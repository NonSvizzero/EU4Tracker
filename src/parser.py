import calendar
import csv
import io
import json
import os
import re
import struct
import uuid
from enum import Enum
from multiprocessing import Process
from zipfile import ZipFile

import numpy as np

from src import ASSETS_DIR
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
    DATE = 9
    KEY = 10


types = {
    1: Types.EQ,
    3: Types.LBR,
    4: Types.RBR,
    12: Types.DATE,  # todo is this always a date? find difference between int and date
    13: Types.FLOAT,
    14: Types.BOOL,
    15: Types.STR,
    20: Types.INT,
    23: Types.STR,  # todo is there difference between the two string opcodes? should this be quoted?
    359: Types.FLOAT5,
    400: Types.FLOAT5
}


class Parser:
    keys = {}
    important_keys = {11854: "countries", 10291: "provinces"}
    whitelist = set()
    chunks = 8

    def __init__(self, stream, filename=None, pattern=None, whitelist=True, human_only_countries=False):
        self.stream = stream
        self.filename = filename
        self.pattern = pattern
        self.human_only_countries = human_only_countries
        self.parsers = []
        self.init()
        self.whitelist = self.whitelist if whitelist else None
        self.curr_code = 0
        self.container = ClausewitzObjectContainer()
        self.last_is_key = False  # boolean used to drop unnecessary keys
        self.funcs = {
            Types.EQ: self.assign,
            Types.LBR: self.open_object,
            Types.RBR: self.close_object,
            Types.DATE: self.read_date,
            Types.INT: self.read_int,
            Types.FLOAT: self.read_float,
            Types.BOOL: self.read_bool,
            Types.FLOAT5: self.read_float5,
            Types.STR: self.read_string,
            Types.KEY: self.read_key
        }

    def init(self):
        if self.keys:
            return
        with open(f"{ASSETS_DIR}/keys.txt") as f:
            for line in f.readlines():
                k, v = line.split()
                k = int(k, 16)
                v = v.rstrip()
                self.keys[k] = v
                self.keys[v] = k
            for k in self.important_keys:
                del self.keys[k]
        with open(f"{ASSETS_DIR}/keys_whitelist.csv") as f:
            r = csv.reader(f)
            self.whitelist.update({k for k, d in r})

    def parse(self, read_header=True):
        if self.pattern:
            self.parse_parallel()
        else:
            if read_header:
                assert self.stream.read(6) == b'EU4bin'
            try:
                while True:
                    self.read_code()
            except struct.error:  # EOF
                self.container.close()
                if self.filename:
                    with open(self.filename, 'w') as f:
                        json.dump(self.container, f)

    @timing
    def parse_parallel(self):
        """Uses multiprocessing to parse a big top-level object faster by splitting the content in chunks and spawning
        workers"""
        content = self.stream.read()
        matches = re.findall(self.pattern, content, flags=re.DOTALL)
        ls = np.array(matches, dtype=np.object_)
        for group in np.array_split(ls, min(self.chunks, len(ls))):
            chunk = b''.join(group)
            self.parsers.append(Parser(stream=io.BytesIO(chunk), filename=str(uuid.uuid4())))  # fixme use tempfiles
        processes = []
        for parser in self.parsers:
            processes.append(Process(target=parser.parse, args=(False,)))
            processes[-1].start()
        for process in processes:
            process.join()
        for parser in self.parsers:
            with open(parser.filename) as f:
                d = json.load(f)
                self.container.update(d)
            os.remove(parser.filename)

    def parse_player_country(self):
        b = self.stream.read()
        tag = b".{4}[A-Z0-9\-]{3}\\\x01\\000\\\x03\\000"  # <str_type><str_len>XXX={
        is_human = b'\\\xae\\\x2c\\\x01\\000'
        pattern = tag + is_human + b".*?\\\xe27\\\x01\\000.*?(?=" + tag + b")"
        country = re.search(pattern, b, flags=re.DOTALL).group(0)
        parser = Parser(stream=io.BytesIO(country))
        parser.parse(read_header=False)
        self.container["countries"] = parser.container

    def read_code(self):
        self.curr_code = self.unpack_data(2, '<H')
        t = types.get(self.curr_code, Types.KEY)
        self.funcs[t]()
        self.last_is_key = t is Types.KEY

    def assign(self):
        drop = self.whitelist and self.last_is_key and self.container.get_last() not in self.whitelist
        self.read_code()
        self.container.name_last(drop=drop)

    def open_object(self):
        self.container = ClausewitzObjectContainer(parent=self.container)
        self.container.parent.append(self.container)

    def close_object(self):
        self.container.close()
        self.container = self.container.parent

    def read_date(self):
        """https://gitgud.io/nixx/paperman/-/blob/master/paperman/src/Util/numberToDate.ts"""
        # todo reverse this and store a map {int: date} pre-calculated so that this can return without calculations
        n = self.unpack_data(4, "i")
        zero_date = 43800000  # year 0. only 1.1.1 seems to be used in years between 0 and ~1300
        if n < zero_date or n > 60000000:  # only parses dates between 1.1.1 and ~ 1850
            if n == 43791240:
                v = '-1.1.1'
            else:
                v = n
        else:
            n = (n - zero_date) // 24
            year, n = divmod(n, 365)
            month = day = 1
            for m in range(1, 12):
                _, month_length = calendar.monthrange(1995, m)
                if n >= month_length:
                    n -= month_length
                    month += 1
                else:
                    break
            day += n
            v = f"{year}.{month}.{day}"
        self.save_data(v)

    def read_int(self):
        v = self.unpack_data(4, "i")
        self.save_data(v)

    def read_float(self):
        v = self.unpack_data(4, "i")
        self.save_data(v / 1000)

    def read_bool(self):
        v = self.unpack_data(1, "?")
        self.save_data(v)

    def read_float5(self):
        v = self.unpack_data(8, 'q')
        self.save_data(v / 32768)

    def read_string(self):
        length = self.unpack_data(2, "h")
        v = self.stream.read(length).decode('windows-1252')
        self.save_data(v)

    def read_key(self):
        try:
            self.save_data(self.keys[self.curr_code])
        except KeyError:
            try:
                k = self.important_keys[self.curr_code]
                self.save_data(k)
                if not self.container.parent:  # top level object, split the content
                    self.read_code()  # read ={
                    b = self.stream.read()
                    # regex pattern used for multiprocessing
                    if k == 'countries':
                        # regex explanation: it uses positive lookahead to match until next country tag is found. For
                        # this reason, a dummy tag is added at the end of the string for the last match to succeed.
                        # Since a country tag can be found inside the active_relations section, we match
                        # innovativeness (\\\xe27) first which ensures the whole country content to be matched.
                        tag = b".{4}[A-Z0-9\-]{3}\\\x01\\000\\\x03\\000"  # <str_type><str_len>XXX={
                        is_human = b'\\\xae\\\x2c\\\x01\\000' if self.human_only_countries else b''
                        pattern = tag + is_human + b".*?\\\xe27\\\x01\\000.*?(?=" + tag + b")"
                        end = b'\x04\x00\xda\x28\x01\x00\x03\x00'  # '}active_advisors={' as encoded by Clausewitz
                        dummy_string = b"ttllFOO\x01\x00\x03\x00"
                    elif k == 'provinces':
                        # each province is identified with an int type. We find int indexes only as province identifiers
                        # so it's safe to use the lazy dot operator to match the whole content
                        tag = b'\x0c\x00.{4}\x01\x00\x03\x00'  # <int_type><4_int_bytes>={
                        pattern = tag + b".*?(?=" + tag + b")"
                        end = b'\x04\x00\x4e\x2e\x01\x00\x03\x00'  # '}countries={' as encoded by Clausewitz
                        dummy_string = b"\x0c\x00IIII\x01\x00\x03\x00"
                    else:
                        raise ValueError
                    match = re.search(re.escape(end), b, flags=re.DOTALL)
                    split = match.start()
                    content, remainder = (io.BytesIO(x) for x in (b[:split] + dummy_string, b[split:]))
                    parser = Parser(stream=content, pattern=pattern)
                    parser.parse()
                    self.container.update(parser.container)
                    self.stream = remainder
            except KeyError:
                k = f"unknown_key_{hex(self.curr_code)}"
                print(k, self.container.parent)
                self.keys[self.curr_code] = k
                self.save_data(k)

    def save_data(self, v):
        self.container.append(v)

    def unpack_data(self, size, ft):
        return struct.unpack(ft, self.stream.read(size))[0]

    @classmethod
    @timing
    def from_zip(cls, filename):
        with ZipFile(filename) as zf:
            with zf.open('meta') as f:
                meta = cls(stream=f, whitelist=False)
                meta.parse()
            with zf.open('gamestate') as f:
                gamestate = cls(stream=f, whitelist=True)
                gamestate.parse()
                # gamestate.parse_player_country()
        return {"meta": meta.container, "gamestate": gamestate.container}


class ClausewitzObjectContainer(dict):
    """This is a dictionary that also behaves like a list in case the container does not have any assignments inside it,
     using an integer index for keys. Integer keys are also used to temporary store unnamed elements before an assign
     operation is executed. Since sometimes the same key is repeated, when the object is closed it will fix duplicate
     keys by putting them inside another container. E.g. the 'advisor' key will be repeated 3 times, when the object is
     closed it will contain 'advisors'={0: {...}, 1: {...}, 2: {...}}"""

    def __init__(self, parent=None, **kwargs):
        super().__init__(**kwargs)
        self.parent = parent
        self.i = 0
        self.duplicate_keys = set()
        self.contains_kw = False

    def append(self, item):
        self[self.i] = item
        self.i += 1

    def close(self):
        if self.contains_kw:
            del self[0]
            del self[1]
        for k, v in list(self.items()):
            if v == {}:
                del self[k]
                continue
            try:
                stripped_key = k.rstrip()
                if stripped_key in self.duplicate_keys:
                    group_key = stripped_key + 's'
                    group = self.setdefault(group_key, ClausewitzObjectContainer(parent=self))
                    group.append(v)
                    del self[k]
            except AttributeError:  # key is an integer, rstrip() returned exception
                pass
        for k in self.duplicate_keys:
            group_key = k + 's'
            if group_key in self and len(self[group_key]) == 1:
                self[k] = self[group_key][0]
                del self[group_key]
        self.duplicate_keys.clear()

    def name_last(self, drop=False):
        try:
            name = self[self.i - 2]
            value = self[self.i - 1]
            self.i -= 2
            self.contains_kw = True
            if drop:
                return
            if name in self and isinstance(name, str):
                self.duplicate_keys.add(name)
                while name in self:
                    name += ' '
            self[name] = value
        except KeyError:
            self.parent.name_last(drop=drop)

    def get_last(self):
        return self[self.i - 1]


if __name__ == '__main__':
    filename = "Bharat"
    d = Parser.from_zip(f"{ASSETS_DIR}/{filename}.eu4")
    with open(f"{ASSETS_DIR}/{filename}.json", 'w') as f:
        json.dump(d, f)
