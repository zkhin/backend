#!/usr/bin/env python

import argparse

# relative imports don't work from scripts, so depending on 'art' to be globally unique
# https://stackoverflow.com/a/16985066
from art import generate_basic_grid


def parse_args():
    parser = argparse.ArgumentParser(description='Generate album art')
    parser.add_argument('-o', dest='output_file', metavar='outputfile', type=argparse.FileType('wb'), required=True,
                        help='file to write output image to')
    parser.add_argument('input_files', metavar='inputfile', type=argparse.FileType('rb'), nargs='+',
                        help='file to read input image from')
    args = parser.parse_args()
    return args.output_file, args.input_files


def main():
    output_file, input_files = parse_args()
    output_buf = generate_basic_grid(input_files)
    output_file.write(output_buf.read())


if __name__ == '__main__':
    main()
