#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import argparse
import json
from pathlib import Path, PurePath
import psycopg2
import re
import os
import subprocess
import sys
import warnings
from itertools import zip_longest
import hashlib
from wand.image import Image

from match import match
from ocr_pmc import get_engines, ocr_pmc
from summarize import summarize
from get_pg_conn import get_pg_conn


CURRENT_SCRIPT_PATH = os.path.dirname(sys.argv[0])
CURRENT_DB_PATH = Path(PurePath(CURRENT_SCRIPT_PATH, "CURRENT_DB"))
CURRENT_DB = open(CURRENT_DB_PATH, "r").read().splitlines()[0]

pmcid_re = re.compile('^(PMC\d+)__(.+)')

# e.g., "Hs_Wnt_Signaling_in_Kidney_Disease_WP4150_94404.png"
wp_re = re.compile('^([A-Z][a-z])_(.+?)_(WP\d+)_(\d+)$')

# from here: https://github.com/wikipathways/wikipathways.org/blob/92e2bb99b3e564e25ba13f557d631e7e5459ca34/wpi/extensions/Pathways/Organism.php#L56
abbr_for_organism = {
    'Anopheles gambiae': 'Ag',
    'Arabidopsis thaliana': 'At',
    'Bacillus subtilis': 'Bs',
    'Beta vulgaris': 'Bv',
    'Bos taurus': 'Bt',
    'Caenorhabditis elegans': 'Ce',
    'Canis familiaris': 'Cf',
    'Clostridium thermocellum': 'Ct',
    'Danio rerio': 'Dr',
    'Drosophila melanogaster': 'Dm',
    'Escherichia coli': 'Ec',
    'Equus caballus': 'Qc',
    'Gallus gallus': 'Gg',
    'Glycine max': 'Gm',
    'Gibberella zeae': 'Gz',
    'Homo sapiens': 'Hs',
    'Hordeum vulgare': 'Hv',
    'Mus musculus': 'Mm',
    'Mycobacterium tuberculosis': 'Mx',
    'Oryza sativa': 'Oj',
    'Pan troglodytes': 'Pt',
    'Populus trichocarpa': 'Pi',
    'Rattus norvegicus': 'Rn',
    'Saccharomyces cerevisiae': 'Sc',
    'Solanum lycopersicum': 'Sl',
    'Sus scrofa': 'Ss',
    'Vitis vinifera': 'Vv',
    'Xenopus tropicalis': 'Xt',
    'Zea mays': 'Zm'
}
organism_for_abbr = {v: k for k, v in abbr_for_organism.items()}

cwd = os.getcwd()
# TODO: should LOGS_DIR use '.', 'cwd' or 'current script path'?
LOGS_DIR="./outputs"
FAILS_FILE_PATH=Path(PurePath(LOGS_DIR, "fails.txt"))

def clear(args):
    target = args.target
    conn = get_pg_conn()

    try:
        if target == "matches" or target == "figures":
            match_attempts_cur = conn.cursor()
            transformed_words_cur = conn.cursor()

            try:
                open(Path(PurePath(LOGS_DIR, "successes.txt")), 'w').close()
                open(FAILS_FILE_PATH, 'w').close()
                open(Path(PurePath(LOGS_DIR, "results.tsv")), 'w').close()

                match_attempts_cur.execute("DELETE FROM match_attempts;")
                transformed_words_cur.execute("DELETE FROM transformed_words;")

            except(psycopg2.DatabaseError) as e:
                print('Database Error %s' % e, '\n', 'clear %s: FAIL' % target)
                raise

            finally:
                if match_attempts_cur:
                    match_attempts_cur.close()
                if transformed_words_cur:
                    transformed_words_cur.close()

        if target == "figures":
            ocr_processors__figures_cur = conn.cursor()
            figures_cur = conn.cursor()

            try:
                ocr_processors__figures_cur.execute(
                    "DELETE FROM ocr_processors__figures;")
                figures_cur.execute("DELETE FROM figures;")

            except(psycopg2.DatabaseError) as e:
                print('Database Error %s' % e, '\n', 'clear %s: FAIL' % target)
                raise

            finally:
                if ocr_processors__figures_cur:
                    ocr_processors__figures_cur.close()
                if figures_cur:
                    figures_cur.close()

        conn.commit()
        print("clear %s: SUCCESS" % target)

    except(psycopg2.DatabaseError) as e:
        print('Database Error %s' % e, '\n', 'clear %s: FAIL' % target)
        conn.rollback()

    except(Exception) as e:
        print('Unexpected Error:', sys.exc_info()[0], '\n', e)
        conn.rollback()

    finally:
        if conn:
            conn.close()


def ocr(args):
    engine = args.engine
    preprocessor = args.preprocessor
    if not preprocessor:
        preprocessor = "noop"
    limit = args.limit
    ocr_pmc(engine, preprocessor, limit)


def load_figures(args):
    figures_dir = args.dir

    figure_paths = list()
    for x in os.listdir(PurePath(cwd, figures_dir)):
        if re.match('.*\.jpg$|.*\.jpeg$|.*\.png$', x, flags=re.IGNORECASE):
            figure_paths.append(Path(PurePath(cwd, figures_dir, x)))

    conn = get_pg_conn()
    papers_cur = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
    figures_cur = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
    organism_cur = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
    pmcs_cur = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)

    pmcid_to_paper_id = dict()

    try:
        papers_cur.execute("SELECT id, pmcid FROM papers;")
        for row in papers_cur:
            pmcid_to_paper_id[row["pmcid"]] = row["id"]

        pmcs_cur.execute("SELECT pmcid FROM pmcs;")
        # TODO This method doesn't work:
        #pmcids = set(pmcs_cur.fetchall()[0])
        # This method does work, but isn't there a better way?
        pmcs_cur_all = pmcs_cur.fetchall()
        pmcids = set()
        for row in pmcs_cur_all:
            pmcids.add(row[0])

        for figure_path in figure_paths:
            filepath = str(figure_path.resolve())
            filename_stem = figure_path.stem
            paper_filename_components = pmcid_re.match(filename_stem)
            wp_filename_components = wp_re.match(filename_stem)
            organism = None
            if paper_filename_components:
                pmcid = paper_filename_components[1]
                figure_number = paper_filename_components[2]
            elif wp_filename_components:
                # not really the pmcid of this figure. kind of a hack.
                # it's the pmcid of the wikipathways paper.
                pmcid = 'PMC4702772'
                organism = organism_for_abbr[wp_filename_components[1]]
                pathway_name = wp_filename_components[2].replace('_', ' ')
                wp_id = wp_filename_components[3]
                wp_version = wp_filename_components[4]
                figure_number = "http://identifiers.org/wikipathways/%s" % (
                    wp_id)
            else:
                raise Exception("Could not parse filepath %s" % filepath)

            print("Processing pmcid: %s figure_number: %s" %
                  (pmcid, figure_number))

            if not pmcid in pmcids:
                msg='{pmcid} not in table pmcs'.format(pmcid=pmcid)
                warnings.warn(msg)
                with open(FAILS_FILE_PATH, "a+") as failsfile:
                    failsfile.write('\n' + msg)
                continue

            paper_id = None
            if pmcid in pmcid_to_paper_id:
                paper_id = pmcid_to_paper_id[pmcid]
            else:
                if organism:
                    papers_cur.execute(
                        "INSERT INTO papers (pmcid, organism_id) VALUES (%s, (SELECT organism_id FROM organism_names WHERE name = %s AND name_class = 'scientific name')) RETURNING id;", (pmcid, organism))
                else:
                    # TODO: getting the organism in these next few steps could probably all be done in one SQL query
                    organism_cur.execute("SELECT organism_id FROM organism2pubtator INNER JOIN pmcs ON organism2pubtator.pmid = pmcs.pmid WHERE pmcs.pmcid = %s LIMIT 1;", (pmcid, ))
                    organism_id = None
                    organism_ids = organism_cur.fetchone()
                    if organism_ids:
                        organism_id=organism_ids[0]
                    else:
                        organism_cur.execute("SELECT organism_id FROM organism2pubmed INNER JOIN pmcs ON organism2pubmed.pmid = pmcs.pmid WHERE pmcs.pmcid = %s LIMIT 1;", (pmcid, ))
                        organism_ids = organism_cur.fetchone()
                        if organism_ids:
                            organism_id=organism_ids[0]
                        else:
                            organism_id = 1
                            msg='Failed to identify organism for {filepath}. Setting organism_id to value of "1" (all).'.format(filepath=filepath)
                            warnings.warn(msg)
                            with open(FAILS_FILE_PATH, "a+") as failsfile:
                                failsfile.write('\n' + msg)

                    papers_cur.execute(
                        "INSERT INTO papers (pmcid, organism_id) VALUES (%s, %s) RETURNING id;", (pmcid, organism_id))

                paper_id = papers_cur.fetchone()[0]
                pmcid_to_paper_id[pmcid] = paper_id

            m = hashlib.sha256()
            with open(filepath, "rb") as image_file:
                m.update(image_file.read())
            figure_hash = m.hexdigest()

            with Image(filename=filepath) as img:
                resolution = int(round(min(img.resolution)))
                figures_cur.execute(
                    "INSERT INTO figures (filepath, figure_number, paper_id, resolution, hash) VALUES (%s, %s, %s, %s, %s);",
                    (filepath, figure_number, paper_id, resolution, figure_hash)
                )

        conn.commit()

        print('load_figures: SUCCESS')

    except(psycopg2.DatabaseError) as e:
        print('Database Error:', sys.exc_info()[0], '\n', e, '\n', 'load_figures: FAIL')

    finally:
        if papers_cur:
            papers_cur.close()
        if figures_cur:
            figures_cur.close()
        if conn:
            conn.close()


def db_copy(args):
    name = args.name
    subprocess.run(["createdb", "-Opfocr", "-T%s" % CURRENT_DB, name])
    with open(CURRENT_DB_PATH, 'w') as f:
        f.write(name)


# Create parser and subparsers
parser = argparse.ArgumentParser(
    prog='pfocr',
    description='''Process figures to extract pathway data.''')
subparsers = parser.add_subparsers(title='subcommands',
                                   description='valid subcommands',
                                   help='additional help')

# create the parser for the "clear" command
parser_clear = subparsers.add_parser('clear',
                                     help='Clear specified data from database.')
parser_clear.add_argument('target',
                          help='What to clear',
                          choices=["figures", "matches"])
parser_clear.set_defaults(func=clear)

# create the parser for the "db_copy" command
parser_db_copy = subparsers.add_parser('db_copy',
                                     help='Create copy of current database and set as current.')
parser_db_copy.add_argument('name',
                          type=str,
                          help='Name of new database')
parser_db_copy.set_defaults(func=db_copy)


# create the parser for the "ocr" command
parser_ocr = subparsers.add_parser('ocr',
                                   help='Run OCR on PMC figures and save results to database.')
parser_ocr.add_argument('engine',
        help='OCR engine to use. Specify one: {}'.format(','.join(get_engines())))
parser_ocr.add_argument('--preprocessor',
                        help='image preprocessor to use. default: no pre-processing.')
parser_ocr.add_argument('--limit',
                        type=int,
                        help='limit number of figures to process')
parser_ocr.set_defaults(func=ocr)

# create the parser for the "load_figures" command
parser_load_figures = subparsers.add_parser('load_figures',
                                            help='Load figures and optionally papers from specified dir')
parser_load_figures.add_argument('dir',
                                 help='Directory containing figures and optionally papers')
parser_load_figures.set_defaults(func=load_figures)

# create the parser for the "match" command
parser_match = subparsers.add_parser('match',
                                     help='Extract data from OCR result and put into DB tables. (See also run.sh)')
parser_match.add_argument('-n', '--normalize',
                          action='append',
                          help='transform OCR result and lexicon')
parser_match.add_argument('-m', '--mutate',
                          action='append',
                          help='transform only OCR result')

# create the parser for the "summarize" command
parser_summarize = subparsers.add_parser('summarize')
parser_summarize.set_defaults(func=summarize)

parser_match.set_defaults(func=match)

args = parser.parse_args()

# from python docs
def grouper(iterable, n, fillvalue=None):
    "Collect data into fixed-length chunks or blocks"
    # grouper('ABCDEFG', 3, 'x') --> ABC DEF Gxx"
    args = [iter(iterable)] * n
    return zip_longest(*args, fillvalue=fillvalue)


raw = sys.argv
normalization_flags = ["-n", "--normalize"]
mutation_flags = ["-m", "--mutate"]
if len(raw) <= 1:
    parser.print_help()
elif raw[1] == "match":
    transforms = []
    for arg_pair in grouper(raw[2:], 2, 'x'):
        category_raw = arg_pair[0]
        category_parsed = ""
        if category_raw in normalization_flags:
            category_parsed = "normalize"
        elif category_raw in mutation_flags:
            category_parsed = "mutate"

        if category_parsed:
            transforms.append(
                {"name": arg_pair[1], "category": category_parsed})

    args.func(transforms)
else:
    args.func(args)
