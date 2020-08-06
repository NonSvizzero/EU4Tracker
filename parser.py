import calendar
import io
import pickle
import sys

import numpy as np
import re
import struct
from datetime import datetime
from enum import Enum
from multiprocessing import Process, Queue, Pipe, connection
from util import timing, func_times

# https://codeofwar.wbudziszewski.pl/2015/07/29/binary-savegames-insight/

class Types(Enum):
    EQ = 1
    LBR = 2
    RBR = 3
    INT = 4
    FLOAT = 5
    BOOL = 6
    FLOAT5 = 7
    STR = 8
    KEY = 9

types = {
    1: Types.EQ,
    3: Types.LBR,
    4: Types.RBR,
    12: Types.INT,  # todo is this always a date? find difference between int and date
    13: Types.FLOAT,
    14: Types.BOOL,
    15: Types.STR,
    20: Types.INT,
    23: Types.STR,  # todo is there difference between the two string opcodes? should this be quoted?
    359: Types.FLOAT5,
    400: Types.FLOAT5
}

escaped = {

}

chunks = {
    "info": ["", "trade", b""],
    # regex: <str_type><str_len>XXX={<lazy_dot>mil_spent={<lazy_dot>}(optional debase_recharge_need)}
    # mil_spent seems to always be last key inside the body of a country description
    "country": ["countries", "active_advisors",
                b".{4}\w{3}\\\x01\\000\\\x03\\000.*?z4\\x01\\000\\\x03\\000.*?\\\x04\\000(?:m4.{8})?\\\x04\\000"],
    "stats": ["income_statistics", "expanded_dip_action_groups", b'']
}


def decode_date(n):
    year = -5000 + n / 24 / 365
    day = 1 + n / 24 % 365
    month = 1
    for m in range(12):
        _, month_length = calendar.monthrange(2015, m)
        if day > month_length:
            day -= month_length
            month += 1
        else:
            break

    return datetime(year, month, day)


class Parser:
    keys = {}
    token = b'\x01\x00\x03\x00'  # '={' as encoded by Clausewitz
    chunks = 4

    def __init__(self, stream, pattern=None):
        self.stream = stream
        self.pattern = pattern
        self.connection = None
        self.parsers = []
        self.parse_keys()
        self.curr_code = 0
        self.curr_container = ClausewitzObjectContainer(self, name="master")
        self.funcs = {
            Types.EQ: self.assign,
            Types.LBR: self.open_object,
            Types.RBR: self.close_object,
            Types.INT: self.read_int,
            Types.FLOAT: self.read_float,
            Types.BOOL: self.read_bool,
            Types.FLOAT5: self.read_float5,
            Types.STR: self.read_string,
            Types.KEY: self.read_key
        }

    @timing
    def search(self):
        """Searches for offsets of the chunks to parse inside the binary string"""
        b = self.stream.read()
        for name, (s, e, pattern) in chunks.items():
            start = (self.keys[s]).to_bytes(2, 'little') + self.token if name != 'info' else b'\x4d\x28'
            end = (self.keys[e]).to_bytes(2, 'little') + self.token
            string = re.escape(start) + b".*" + re.escape(end)
            p = re.compile(string, flags=re.DOTALL)
            r = re.search(p, b)
            stream = io.BytesIO(r.group()[:-6])  # excludes next token
            parser = Parser(stream=stream, pattern=pattern)
            self.parsers.append(parser)
        self.launch_threads()

    @timing
    def parse(self, connection=None):
        self.connection = connection
        if self.pattern:
            self.parse_parallel()
        else:
            try:
                while True:
                    self.read_code()
            except KeyError as e:
                cursor = self.stream.tell()
                dump = self.stream.read()
                raise ValueError(f"{e}\nUnrecognized key at @{cursor}: {dump[cursor+10]}")
            except struct.error:
                pass
        if self.connection:
            # todo extract only relevant data, can't send back all object (too big and inneficient)
            self.connection.send_bytes(b'0')
            self.connection.close()

    def parse_parallel(self):
        """Uses multiproc to parse a big top-level object faster by splitting the content in chunks"""
        self.read_code()  # read token
        self.read_code()  # read '={'
        content = self.stream.read()[:-2]  # leaves out closing bracket
        matches = re.findall(self.pattern, content, flags=re.DOTALL)
        ls = np.array(matches, dtype=np.object_)
        for i, group in enumerate(np.array_split(ls, self.chunks)):
            chunk = b''.join(group)
            self.parsers.append(Parser(io.BytesIO(chunk)))
        self.launch_threads()
        self.close_object()

    def update(self, p):
        """Updates this parser with the information from another"""
        self.curr_container.objects.extend(p.curr_container.objects)
        self.curr_container.map.update(p.curr_container.map)

    def launch_threads(self):
        processes = []
        readers = []
        for p in self.parsers:
            r, w = Pipe(duplex=False)
            readers.append(r)
            p.connection = w
            processes.append(Process(target=p.parse, args=(w,)))
            processes[-1].start()
            w.close()
        while readers:
            for r in connection.wait(readers):
                try:
                    msg = r.recv_bytes()
                    # p = pickle.loads(msg)
                    # self.update(p)
                except EOFError:
                    r.close()
                    readers.remove(r)
                else:
                    pass
        print("Pipes cleared")
        for p in processes:
            p.join()
            p.terminate()

    def parse_keys(self):
        if self.keys:
            return
        with open("keys.txt") as f:
            for line in f.readlines():
                k, v = line.split()
                k = int(k, 16)
                v = v.rstrip()
                if k not in types:
                    self.keys[k] = v
                    self.keys[v] = k
                else:
                    print(f"Meaning of key {hex(k)}: {v}")

    def read_code(self):
        self.curr_code = self.unpack_data(2, '<H')
        t = types.get(self.curr_code, Types.KEY)
        return self.funcs[t]()

    def assign(self):
        name = self.curr_container.objects.pop().value
        self.read_code()
        try:
            self.curr_container.name_last(name)
        except IndexError:
            self.curr_container.parent.name_last(name)

    def open_object(self):
        self.curr_container = ClausewitzObjectContainer(self, parent=self.curr_container)
        self.curr_container.parent.objects.append(self.curr_container)

    def close_object(self):
        self.curr_container = self.curr_container.parent

    def read_int(self):
        v = self.unpack_data(4, "I")
        self.save_data(v)

    def read_float(self):
        v = self.unpack_data(4, "I")
        self.save_data(v / 1000)

    def read_bool(self):
        v = self.unpack_data(1, "?")
        self.save_data(v)

    def read_float5(self):
        v = self.unpack_data(8, 'Q')
        self.save_data(v / 32768)

    def read_string(self):
        length = self.unpack_data(2, "H")
        v = self.stream.read(length).decode('windows-1252')
        self.save_data(v)

    def read_key(self):
        self.save_data(self.keys[self.curr_code])

    def save_data(self, v):
        o = ClausewitzObject(v)
        self.curr_container.objects.append(o)

    def unpack_data(self, size, ft):
        return struct.unpack(ft, self.stream.read(size))[0]


class ClausewitzObjectContainer:
    def __init__(self, parser, name=None, parent=None):
        self.parser = parser
        self.name = name
        self.map = {}
        self.objects = []
        self.parent = parent

    def __repr__(self):
        return self.name

    def __getitem__(self, item):
        return self.map[item]

    def name_last(self, name):
        last = self.objects[-1]
        last.name = name
        self.map[name] = last


class ClausewitzObject:
    def __init__(self, value):
        self.name = None
        self.value = value
        # todo recognize dates

    def __str__(self):
        if self.name:
            return f"{self.name}={self.value}"
        else:
            return str(self.value)

    def __repr__(self):
        return self.__str__()


if __name__ == '__main__':
    with open("binary.eu4", "rb") as f:
        p = Parser(f)
        p.search()
        print(func_times, len(p.curr_container.objects))
