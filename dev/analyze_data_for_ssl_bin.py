#!/usr/bin/env python3
import sys

from construct import *
import pandas as pd
from icecream import ic




#dfs_string = PascalString(VarInt, "utf8")
dfs_string = PascalString(Int16ul, "utf8")
#dfs_string = Struct(\
#    "str" / PascalString(VarInt, "utf8")),

if 1:
    coord = Float32l
    drop_rows = [3,4,5,7,9,11] # for Float32l
    cvt = lambda x: int(x * 100)
else:
    coord = Int16ul
    drop_rows =  [6,7,11,14,15,18,19,22,23] # for int16
    cvt = lambda x: x
#coord = Float64l
#coord = Int64ub
#coord = Int16ul
#ic(dir(Int32ub))
#ic(Int32ub.sizeof())
coord_cnt = 12 * 4 // coord.sizeof()


item_struct = Struct(\
    "item_id" / dfs_string,
    "task_id" / dfs_string,
#    "dummy" / Byte[139],
    "some_floats" / coord[coord_cnt],
#    "some_floats" / Float64b[6],
#    "some_floats" / Int64ul[6],
#    "some_floats" / Int64ub[6],
#    "x" / coord,
#    "y" / coord,
#    "z" / coord,
#    "a" / coord,
#    "b" / coord,
#    "c" / coord,
#    "junk" / Hex(Int32ul[20]),
#    "dummy" / Byte[139 - 4 * 12 - 4 * 20],
#    "unknown" / Byte[12],
#    "unknown" / Int16ul[6],
#    "masks" / Int16ul[14],
#    "unknown" / Int32ul[3],
#    "dummy" / Int16ul[45],
#    "unknown" / Byte[89 - 48],
    "unknown" / Byte[17],
#    "unknown_nums" / Int32ul[6],
    "masks" / Int32ul[6], # seems to be always FF FF 7F 7F or 7F FF FF 7F 7F, the same value sacrsoss trucks
    "cargo_cnt" / Int32ul,
    "cargo_strings" / dfs_string[this.cargo_cnt],
    "unknown_strings" / dfs_string[7], # 3 * 7 = 21
    "unknown_num" / Int32ul,
    "unknown_string" / dfs_string,
#    Probe(),
#    "dummy2" / Int16ul[23],
#    "dummy" / Byte[46-28],
    "dummy" / Byte[18],
#    "dummy" / Byte[(139 - 4 * 12 - 12)-1],
#    "dummy" / Int16ul[(139 - 4 * 12 - 12)//2],
#    "dummy" / Int16ul[(139 - 4 * 12 - 12)//2],
#    "dummylastbytes" / Byte[1],
#    "dummy" / Byte[139 - 4 * 12],
    )

ic(Switch)

dfs_struct = Struct(\
#    "magic" / Const(0x13415BE, ),
    "magic" / OneOf(Int32ul, (0x13415BE, 20190655)),

#    "hdr" / Byte[22-4],
#    "hdr" / Int16ul[11-2],
    "hdr1" / Int32ul[1],
    "filesize" / Int32ul,
#    "hdr2" / Float32l[1],
    "hdr2" / Int32ul[1],
#    "hdr2" / Int16ul[2],
#    "hdr2" / Byte[4],
    "hdr3" / Int16ul[3],
#    PrintContext("pc"),
#    "len" / Int16ul,
    "name_id" / dfs_string,
    "name_desc_id" / dfs_string,
    "night_day_strings" / dfs_string[8],
    "night_day_last" / Switch(this.magic, { 0x13415BE: dfs_string, 20190655: Int32ul }),
#    "night_day_last" / Switch("garbage", { 0x13415BE: dfs_string, 20190655: Int32ul })
#    Probe(),
#    "dummy2" / Byte[7],
    "sky_id" / dfs_string,
    "sky_sound_id" / dfs_string,
    "item_cnt" / Int32ul,
#    "sky_amb_id" / dfs_string,
    Probe(),
    "item_list" / item_struct[this.item_cnt],
    "after_trucks1" / Int32sl, # 4 in 1/5 levels examined, rest were -1
    "after_trucks2" / Int32sl, # 150-220
    "after_trucks3" / Byte[24], # repeated acros 5 levels
#    "after_trucks" / Byte[32],
    "after_trucks" / Int32ul[32], # seems to be 4 byte value until prox 1390576 (us_16_01) 1390032 (us_01_01)
    )


dfs_file = Struct(\
    # header
    "dfs" / dfs_struct,
#    PrintContext("pc"),
#    "fields" / IfThenElse(this.mdb.newhdr,
#        field_struct[this.mdb.flds],
#        old_field_struct[this.mdb.flds],
#        ),
#    "topics" / IfThenElse(this.mdb.newhdr,
#        field_struct[this.mdb.subflds],
#        old_field_struct[this.mdb.subflds],
#        ),
#
#    "EndOfHdr" / Tell,

    )


def make_table(data, headers, do_cvt = False):
#    df = tabulate(data, headers = headers)
    if do_cvt:
        data = [list(map(cvt, row)) for row in data]

    df = pd.DataFrame(data, columns=headers)
    df['Min_Value'] = df[headers].min(axis=1)
    df['Max_Value'] = df[headers].max(axis=1)
    df['diff'] = df['Max_Value'] - df['Min_Value']
    return df

def display_table(title, df):
    print(f"{title}:")
    print(df)

def header_data(dfs):
    return dfs.hdr1 + dfs.hdr2 + dfs.hdr3

def abbr(s):
    return (s.replace("semitrailer", "strlr").replace("trailer", "trlr").replace("heavy", "hvy").replace("construction", "const")
        .replace("international", "intl").replace("offroad", "ofrd").replace("foldable", "fldbl").replace("equipment", "eqpmt")
        .replace("crane", "crn").replace("chevrolet", "chevy").replace("sideboard", "sbrd").replace("flatbed", "fbed").replace("service", "svc")
        .replace("scout", "sct").replace("fleetstar", "fstar"))


def get_header(level):
#    with open(f"O:\Games\snowrunner\{level}\data_for_ssl.bin", "rb") as in_file:
    with open(f"O:\Games\snowrunner\data_for_ssl_files\{level}_data_for_ssl.bin", "rb") as in_file:
        try:
            parsed = dfs_file.parse_stream(in_file)
        except Exception as e:
            print(f"Error occurred: {e}")
            sys.exit(1)
        return parsed.dfs


def main(fname):
#    levels = ["level_us_16_01", "level_us_16_02", "level_us_16_03", "level_us_01_01", "level_us_01_02"]#[2:3]
    levels = ["level_us_18_01", "level_us_18_02"]#[2:3]
    levels = ["level_US_12_01"]

    if 0:
        with open(fname, "rb") as in_file:
            parsed = dfs_file.parse_stream(in_file)
            dfs = parsed.dfs
#    print(parsed)


        for item in dfs.item_list:
            print(f"{item.item_id}: {item.task_id}")

#    picked_floats = itemgetter(6,8,10)
#    all_floats = set(range(len(dfs.item_list[0]).some_floats)) - set([6,14,15,])


#    use_items = dfs.item_list[:8]
#    use_items = itemgetter(1,2,3,12,13)(dfs.item_list)
#        use_items = itemgetter(1,2,3)(dfs.item_list)
        use_items = dfs.item_list[:10]
        display_table("some_floats", make_table(list(zip(*(item.some_floats for item in use_items))), headers = [abbr(item.item_id) for item in use_items], do_cvt=True))
        df = make_table(list(zip(*(item.some_floats for item in use_items))), headers = [abbr(item.item_id) for item in use_items], do_cvt=True)
        df_dropped = df.drop(drop_rows, axis=0)
        display_table("picked some_floats", df_dropped)
        display_table("unknown", make_table(list(zip(*(item.unknown for item in use_items))), headers = [abbr(item.item_id) for item in use_items]))
#        display_table("unknown_nums", make_table(list(zip(*(item.unknown_nums for item in use_items))), headers = [abbr(item.item_id) for item in use_items]))
        display_table("dummy", make_table(list(zip(*(item.dummy for item in use_items))), headers = [abbr(item.item_id) for item in use_items]))
#    display_table("picked some_floats", make_table(list(zip(*(picked_floats(item.some_floats) for item in use_items))), headers = [abbr(item.item_id) for item in use_items]))
#        display_table("unknown", make_table(list(zip(*(item.unknown for item in use_items))), headers = [abbr(item.item_id) for item in use_items]))
    elif 0:

#    ic(dfs.filesize, dfs2.filesize, dfs3.filesize)
#    display_table("headers", make_table(list(zip(header_data(dfs), header_data(dfs2), header_data(dfs3))), headers = [level[6:] for level in levels]))
        headers = [level[6:] for level in levels]
        dfss = [get_header(level) for level in levels]

        display_table("filesize", make_table(list(zip(*([parsed.filesize] for parsed in dfss))), headers = headers))
#        display_table("headers", make_table(list(zip(*(header_data(parsed) for parsed in dfss))), headers = headers))
        display_table("hdr1", make_table(list(zip(*(dfs.hdr1 for dfs in dfss))), headers = headers))
        display_table("hdr2", make_table(list(zip(*(dfs.hdr2 for dfs in dfss))), headers = headers))
        display_table("hdr3", make_table(list(zip(*(dfs.hdr3 for dfs in dfss))), headers = headers))
        display_table("after_trucks", make_table(list(zip(*(dfs.after_trucks for dfs in dfss))), headers = headers))
    else:
        for level in levels:
            dfs = get_header(level)
            print(f"{level}: {dfs.name_id}")

            for item in dfs.item_list:
                print(f"    {item.item_id}: {item.task_id}, {item.unknown_string}")

                for cargo_string in item.cargo_strings:
                    print(f"        {cargo_string}")



if __name__ == "__main__":
#    main("O:\Games\snowrunner\level_us_16_02\data_for_ssl.bin")
#    main("O:\Games\snowrunner\level_us_01_01\data_for_ssl.bin")
    main("O:\Games\snowrunner\data_for_ssl_files\level_us_18_02_data_for_ssl.bin")

