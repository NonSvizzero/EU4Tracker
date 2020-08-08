import calendar
import io
import pickle
from zipfile import ZipFile

import numpy as np
import re
import struct
from datetime import datetime
from enum import Enum
from multiprocessing import Process, Pipe, connection
from util import timing


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
    assign_t = b'\x01\x00\x03\x00'  # '={' as encoded by Clausewitz
    chunks = 8

    def __init__(self, stream, pattern=None):
        self.stream = stream
        self.pattern = pattern
        self.connection = None
        self.parsers = []
        self.parse_keys()
        self.curr_code = 0
        self.container = ClausewitzObjectContainer()
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
    def search(self, chunks):
        """Searches for offsets of the chunks to parse inside the binary string"""
        b = self.stream.read()
        for name, (s, e) in chunks.items():
            start = b"" if s is None else (self.keys[s]).to_bytes(2, 'little') + self.assign_t
            end = b"" if e is None else (self.keys[e]).to_bytes(2, 'little') + self.assign_t
            string = re.escape(start) + b".*" + re.escape(end)
            p = re.compile(string, flags=re.DOTALL)
            r = re.search(p, b)
            match = r.group()
            stream = io.BytesIO(match[:-6])  # excludes 'next_token={' from the match
            # regex pattern used for multiprocessing  TODO pattern for provinces
            if name == 'country':
                tag = b".{4}[A-Z0-9\-]{3}\\\x01\\000\\\x03\\000"  # <str_type><str_len>XXX={
                # regex explanation: it uses positive lookahead to match until next country tag is found. For this
                # reason, a dummy tag is added at the end of the string for the last match to succeed. The end of a
                # country section is either '}}' or 'government_reform_progress=<int>bbbb}'
                pattern = tag + b".*?(?:(?:\\\x04\\000){2,}|\\ 8\\\x01\\000.{6}\\\x04\\000)(?=" + tag + b")"
                stream = io.BytesIO(match[:-8] + b"xxxxFOO\x01\x00\x03\x00\x04\x00")
            else:
                pattern = None
            parser = Parser(stream=stream, pattern=pattern)
            parser.parse()
            self.parsers.append(parser)

    @timing
    def parse(self, connection=None, read_header=False):
        if read_header:
            assert self.stream.read(6) == b'EU4bin'
        self.connection = connection
        if self.pattern:
            self.parse_parallel()
        else:
            try:
                while True:
                    self.read_code()
            except struct.error:  # EOF
                pass
        if self.connection:
            # todo extract only relevant data, can't send back all object (too big and inefficient)
            history = self.container.popitem()[1].get("history", None)
            if history:
                self.connection.send_bytes(pickle.dumps(history))
            self.connection.close()

    def parse_parallel(self):
        """Uses multiproc to parse a big top-level object faster by splitting the content in chunks and spawning
        workers"""
        self.read_code()  # read token
        self.read_code()  # read '={'
        content = self.stream.read()[:-2]  # leaves out closing bracket
        matches = re.findall(self.pattern, content, flags=re.DOTALL)
        ls = np.array(matches, dtype=np.object_)
        for group in np.array_split(ls, self.chunks):
            chunk = b''.join(group)
            self.parsers.append(Parser(stream=io.BytesIO(chunk)))
        self.launch_processes()
        self.close_object()

    def launch_processes(self):
        processes = []
        readers = []
        msgs = []
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
                    msgs.append(r.recv_bytes())
                except EOFError:
                    readers.remove(r)
                    r.close()

        for p in processes:
            p.terminate()
        for m in msgs:
            # todo parse messages
            # p = pickle.loads(m)
            # print(list(p.keys()))
            pass

    def parse_keys(self):
        if self.keys:
            return
        with open("src/Assets/keys.txt") as f:
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
        self.read_code()
        self.container.name_last()

    def open_object(self):
        self.container = ClausewitzObjectContainer(parent=self.container)
        self.container.parent.append(self.container)

    def close_object(self):
        self.container.close()
        self.container = self.container.parent

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
        try:
            self.save_data(self.keys[self.curr_code])
        except KeyError:
            k = f"unknown_key_{hex(self.curr_code)}"
            print(k)
            self.save_data(k)

    def save_data(self, v):
        self.container.append(v)

    def unpack_data(self, size, ft):
        return struct.unpack(ft, self.stream.read(size))[0]

    @classmethod
    def from_zip(cls, filename):
        chunks = {
            "pre": [None, "countries"],
            "country": ["countries", "active_advisors"],
            "stats": ["income_statistics", None]
        }
        with ZipFile(filename) as zf:
            with zf.open('meta') as f:
                meta = cls(stream=f)
                meta.parse(read_header=True)
            with zf.open('gamestate') as f:
                gamestate = cls(stream=f)
                # gamestate.parse(read_header=True)
                gamestate.search(chunks)
        # todo join info
        return gamestate


class ClausewitzObjectContainer(dict):
    """This is a dictionary that also behaves like a list in case the container does not have any assignments inside it,
     using an integer index for keys. Integer keys are also used to temporary store unnamed elements before an assign
     operation is executed."""

    def __init__(self, parent=None, **kwargs):
        super().__init__(**kwargs)
        self.parent = parent
        self.i = 0

    def append(self, item):
        self[self.i] = item
        self.i += 1

    def close(self):
        if any(isinstance(k, str) for k in self.keys()):
            del self[0]
            del self[1]

    def name_last(self):
        try:
            name = self[self.i - 2]
            value = self[self.i - 1]
            self[name] = value
            self.i -= 2
        except KeyError:
            self.parent.name_last()


if __name__ == '__main__':
    p = Parser.from_zip("src/Assets/emperor.eu4")
