#!/usr/bin/python

"""Generates web bibliography from DBLP

The resulting webpage is self-contained, but may reference external resources such as .js or .css 
files, depending on the template used. The default template includes js-powered interactive
filtering based on author, year, and venue

Relies on DBLP's well-curated bibtex and predictable behavior by citeproc-java to build correct 
webpages. Using less-consistent bibtex and/or a different bibtex-to-html engine will probably break
stuff.

Requires:
    a list of dblp-bib-url author-id pairs, to know what to download
    an internet connection to actually download the bibliography
    citeproc-java-tool-2.0.0 (see help for download link) to format it as ieee-with-url
       
"""

import bs4 as bs
import bibtexparser as btp
import argparse
import sys, re
import requests
import time, datetime
import json
from subprocess import call

def read_items(html, url_to_html):
    doc = bs.BeautifulSoup(
        f"<!DOCTYPE html><html><body>${html}</body></html>", 
        "html5lib")
    for item in doc.find_all('li'):
        if item.a is None:
            print(f"No URL for {item}")
            continue
        url_to_html[item.a['href']] = item

def replace_escapes(str, char, eq):
    """Replaces a set of latex diacriticals
        
       for example, replace_escapes(text, "'", "aáeéiíoóuúAÁEÉIÍOÓUÚ") => fixes acute accents
    """
    for i in range(0, len(eq)-1, 2):
        # {\'{a}} => á
        str = str.replace(f"{{\\{char}{{{eq[i]}}}}}", eq[i+1])
    return str

def fix_escapes(text):    
    """Replaces a set of latex escapes by unicode equivalents

       Should keep bibtex author names safe - does not attempt to replace { } or {_}, for example
    """
    text = replace_escapes(text, "'", "aáeéiíoóuúAÁEÉIÍOÓUÚ")
    text = replace_escapes(text, '"', "aäeëiïoöuüAÄEËIÏOÖUÜ")
    text = replace_escapes(text, "`", "aàeèiìoòuùAÀEÈIÌOÒUÙ")
    text = text.replace("{\'{i}}", "í")
    text = text.replace("{\\~{a}}", "ã")
    text = text.replace("{\\~{n}}", "ñ")
    text = text.replace("{\\c{c}}", "ç")
    return text

def fix_bibtex_url(url):
    """Replaces latex escapes in urls
    """
    # http://ixdea.uniroma2.it/inevent/events/idea2010/index.php?s=10&#38;#38;a=10&#38;#38;link=ToC_45_P&#38;#38;link=45preface_fs
    # http://ixdea.uniroma2.it/inevent/events/idea2010/index.php?s=10\&\#38;a=10\&\#38;link=ToC\_45\_P\&\#38;link=45preface\_fs
    url = re.sub(r"\\_", "_", url)
    url = re.sub(r"\\&", "&", url)
    url = re.sub(r"\\#", "#", url)
    url = re.sub(r"\\%", "%", url)
    url = url.replace("&#38;", "&")
    return url

def fix_authors(text):
    """Fixes author names
    
       cannot be called before bibtex is processed, because authors-parts would be broken
    """
    text = text.replace("{-}", "-")
    text = text.replace("{ }", " ")
    return text

def fix_initial(text):
    """Initial post-download fixes
    
    """
    # some pages are actually html with <pre> snippets...
    text = re.sub(r"^<.*$", "", text, flags=re.MULTILINE)
    text = text.replace("&apos;", "\'")
    text = text.replace("&quot;", "\"")

    # {\i} => {i}
    text = re.sub(r"\{\\([a-z])\}", r"{\1}", text)
    text = fix_escapes(text)
    return text

def download_bib_author(url, author_name):
    """Downloads an author bibliography from DBLP

       Attempts to strip stray HTML (= *can* handle ?view=bibtex urls)
       Writes to author_name.bib file, after many latex escapes with unicode characters
    """
    print(f"\tretrieving bibliography for {author_name} from {url}...")
    start = time.perf_counter()
    r = requests.get(url)
    print(f"    -- retrieved in {time.perf_counter() - start}s!")
    text = fix_initial(r.text)
    text = fix_escapes(text)
    with open(f"{author_name}.bib", 'w') as author_bib_f:
        author_bib_f.write(text)

def download_bibs(authors_file, delay=1):
    """Downloads author bibliograhies from DBLP

       Format must be one author per line, with author_bibtex_url author_key per line
       Writes a .bib file for each author key with the contens retrieved from the author url
    """
    print(f"downloading author bibliographies specified in {authors_file} from DBLP...")
    with open(authors_file, 'r') as authors_f:
        authors = json.loads(authors_f.read())
        
    for username, author in authors.items():        
        url = f"https://dblp.uni-trier.de/pid/{author['id']}"
        url += ".bib" if re.match("[0-9]+/[0-9]+", author['id']) else ".html?view=bibtex"
        download_bib_author(url, username)
        time.sleep(delay)
    
def filter_bibs(authors_file, first_year, last_year, bib_file):  
    """Filters author bibliographies

       Retains only those between given years
       Removes duplicates
       Adds a non-standard bibtex key with the DBLP IDs of authors (only those in authors_file)
       Adds fake urls to papers without DOI or url, using https://localhost/dblp-key 
            since the fake url will appear in html output, it allows linking back to the bibtex entry
    """      
    print(f"filtering author bibliographies from files, retaining those between {first_year} and {last_year} inclusive:\n", end='')
    bibauthors = {}
    bibitems = []
    duplicates = 0
    global_total = 0
    filtered = 0
    with open(authors_file, 'r') as authors_f:
        authors = json.loads(authors_f.read())
    for username, author in authors.items():
        author_id = author['id']
        author_bib = f"{username}.bib"
        with open(author_bib, 'r') as author_bib_f:
            print(f"\t{author_bib}", end=' ')
            items = re.split(r"\n\n+", author_bib_f.read())
            total = 0
            selected = 0
            for item in items:
                if len(item) == 0: continue
                global_total += 1
                try:
                    # @inproceedings{DBLP:conf/its/MartinezSMLA00,
                    id = re.search(r"\{DBLP:([^,]+),",
                            item, flags=re.MULTILINE).group(1)
                    year = int(re.search(r"^  year\s+=\s+\{([0-9]+)\},", 
                            item, flags=re.MULTILINE).group(1))
                    has_url = re.search(r"^  url\s+=\s+\{([^}]+)\},", 
                            item, flags=re.MULTILINE)
                    has_doi = re.search(r"^  doi\s+=\s+\{([^}]+)\},", 
                            item, flags=re.MULTILINE)
                    if has_url is None and has_doi is None:
                        # inject fake url to ensure match later; must remove when fixing html
                        item = re.sub(r"^(  year)",
                                f"  url          = {{https://localhost/{id}}},\n\\1",
                                item, flags=re.MULTILINE)
                    elif has_url is not None:
                        url = re.search(r"^  url\s+=\s+\{([^}]+)\},", 
                            item, flags=re.MULTILINE).group(1)
                        fixed = fix_bibtex_url(url)
                        if url != fixed:
                            item = item.replace(url, fixed)
                    total += 1
                    if first_year <= year and year <= last_year:
                        selected += 1
                        filtered += 1
                        if id not in bibauthors: 
                            bibauthors[id] = [author_id]
                            bibitems.append(item)
                        else:
                            duplicates += 1
                            bibauthors[id].append(author_id)
                except AttributeError as _:
                    print(f"(bad: >>{item}<<)", end='')
            print(f"({selected}/{total})")                       

    # and write output, enriched with dblp author ids
    with open(bib_file, 'w') as bib_f:
        for item in bibitems:
            id = re.search(r"\{DBLP:([^,]+),",
                    item, flags=re.MULTILINE).group(1)            
            author_ids = "{" + ",".join(bibauthors[id]) + "}"
            item = re.sub(r"(dblp.org})$", f"\\1,\n  dblpid       = {author_ids}", item, flags=re.MULTILINE)
            bib_f.write(item)
            bib_f.write("\n\n")
    print(f"\tchose {filtered-duplicates} items from {global_total}, avoiding {duplicates} duplicates")

def generate_html(bib_file, citeproc_executable, html_file):
    """Generates html using ieee-with-url format for all references in a bib file

       Requires citeproc-java-tool to be installed in provided location
    """
    call_string = [citeproc_executable] \
        + ['-o', html_file ] \
        + ['bibliography' ] \
        + ['-i', bib_file ] \
        + ['-s', 'ieee-with-url' ] \
        + ['-f', 'html' ]
    print(f'calling citeproc-java to format refs in {bib_file} as ieee html:\n\t{call_string}')
    try:
        retcode = call(call_string, stderr=sys.stderr, stdout=sys.stdout)
        if retcode < 0:
            raise SystemExit(f"citeproc-java-tool was terminated by signal {-retcode}, aborting")
    except OSError as e:
        raise SystemExit(f"Execution of citeproc-java-tool failed: {e}, aborting")    
    
    with open(html_file, 'r') as html_f: html = html_f.read()
    # hyperlink dois
    html = re.sub(r' \[Online.*doi.org/([^<]*)', 
                  r'. DOI: <a href="https://doi.org/\1">\1</a>', html)
    # hyperlink non-dois; [Online]. Available <url> => [Online]. Available <linked url>
    html = re.sub(r' Available: (http[^ \n]*)', 
                  r' Available: <a href="\1">\1</a>', html)
    # remove <div> start and end tags
    html = re.sub(r'<[/]*div[^>]*>', 
                  r'', html)
    # replace [123] by a <li>
    html = re.sub(r'\[[0-9]+\]', 
                  r'<li>', html)
    # close <li> (relying on 1 per line)
    html = re.sub(r'>$', r'></li>\n', html, flags=re.MULTILINE)
    
    with open(html_file, 'w') as html_f: html_f.write(html)

def extract_venue(dblpid):
    venue = dblpid.replace("DBLP:", "")
    venue = re.sub(r"/[^/]+$", "", venue, flags=re.MULTILINE)
    return venue

def fix_html(source_file, authors_file, bib_file, template_file, output_file):  
    """Fix html generated by citeproc-java-tool to make it searchable/filterable via JS

       Also removes fake https://localhost/ urls used to link refs without URLs back to bibtex
    """
    print(f"fixing refs in {source_file} to allow filtering by year & authors in {bib_file}")

    # note: docs at /home/mfreire/.local/lib/python3.10/site-packages/bibtexparser
    # see https://github.com/sciunto-org/python-bibtexparser/blob/main/examples/quickstart.ipynb
    with open(bib_file, 'r') as bib_f:
        library = btp.load(bib_f) 

    url_to_bibitem = {}       
    items_without_url = 0
    total_items = 0
    for i, entry in enumerate(library.entries):
        if 'url' not in entry:
            items_without_url += 1
            print(f"No URL in {entry['ID']} (from {entry['year'] if 'year' in entry else '???'})")
        url_to_bibitem[entry['url']] = entry
        total_items += 1
    print(f"\tfound {total_items} items in bibliography, of which {items_without_url} cannot be linked due to missing url")

    url_to_html = {}
    with open(source_file, 'r') as source_f:
        read_items(source_f.read(), url_to_html)
    
    with open(authors_file, 'r') as authors_f:
        authors = authors_f.read()

    items_without_url = 0
    total_items = 0
    with open(template_file, 'r') as template_f:
        pre_template, post_template = template_f.read().split('$ITEMS_GO_HERE$', 1)
    pre_authors, post_authors = pre_template.split("$AUTHORS_GO_HERE$", 1)
    with open(output_file, 'w') as output_f:
        output_f.write(pre_authors)
        output_f.write(authors)
        output_f.write(post_authors)
        for key, fragment in url_to_html.items():
            if key not in url_to_bibitem:
                print(f"url not in bib: {key}")
                items_without_url+=1
                continue
            bib = url_to_bibitem[key]
            fragment['data-dblpid'] = bib['ID']
            fragment['data-authors'] = bib['dblpid']
            fragment['data-year'] = bib['year']
            fragment['data-venue'] = extract_venue(bib['ID']),
            fragment['class'] = 'bibitem'
            text = str(fragment)
            if re.search(r"https://localhost", text) is not None:
                # this is a false URL; must be removed
                text = re.sub(r" \[Online\].*", "</li>", text)
            output_f.write(f"{text}\n")
            total_items +=1
        output_f.write(post_template)
    print(f"\tfixed {total_items} references, could not fix {items_without_url}; after applying template {template_file}, output written to {output_file}");

def abort_if_missing(required_args, args):
    """Used to early-warn users that they are missing required parameters
    
       note: must have used default=argparse.SUPPRESS in corresponding parser.add_argument
    """
    for arg in required_args:
        if arg not in args:
            raise SystemError(f"Missing argument for option: {arg}")

if __name__ == '__main__':      
    year = datetime.date.today().year
    five_years_ago = year-5
    example_author_entry = """
         "mfreire": {
             "id": "232/9796",
             "full": "Manuel Freire Morán"
         },
    """

    parser = argparse.ArgumentParser(description=\
        "Download bibliography from a set of authors from DBLP and prepare it for a website")
    parser.add_argument("--mode", default="all",
            help="Step of processing: 'download', 'filter', 'generate_html', 'fix_html', or 'all' (default)")
    parser.add_argument("--authors_file", 
            help="A json file with a single object, where the keys (with no spaces) are used to name downloaded author bibliographies, and for each author there is both a DBLP ID (either x/y, where both x and y are integers; or a/b, where a is a single letter and b is an actual name), and a full name. For example, for the author of this program, the entry could look like:\n{example_author_entry}", default=argparse.SUPPRESS)    
    parser.add_argument("--first_year", 
            help=f"First year for filtered pubs (default: {five_years_ago})", type=int, default=five_years_ago)  
    parser.add_argument("--last_year", 
            help=f"Last year for filtered pubs (default: {year})", type=int, default=year)
    parser.add_argument("--citeproc_executable", 
            help="Full path to citeproc-java-tool-2.0.0 executable; download from https://github.com/michel-kraemer/citeproc-java/releases/download/2.0.0/citeproc-java-tool-2.0.0.zip",
            default="citeproc-java-tool-2.0.0/bin/citeproc-java")
    parser.add_argument("--html_file", 
            help="An html-fragment file. Generated by 'generate_html'",default=argparse.SUPPRESS)  
    parser.add_argument("--bib_file", 
            help="A bibtex bibliography, with metadata to inject. Generated by 'download'",default=argparse.SUPPRESS)               
    parser.add_argument("--output_file", 
            help="Where to write the output, enriched html file", default=argparse.SUPPRESS)
    parser.add_argument("--template_file", 
            help="Template html to use for output file (default: 'template.html')", default="template.html")
    args = parser.parse_args()
    
    match args.mode:
        case 'download':
            abort_if_missing(['authors_file'], args)
            download_bibs(args.authors_file)
        case 'filter':
            abort_if_missing(['authors_file', 'bib_file'], args)
            filter_bibs(
                args.authors_file, 
                args.first_year, 
                args.last_year, 
                args.bib_file)
        case 'generate_html':
            abort_if_missing(['bib_file', 'html_file'], args)
            generate_html(
                args.bib_file, 
                args.citeproc_executable,
                args.html_file)
        case 'fix_html':
            abort_if_missing(['html_file', 'authors_file', 'bib_file', 'output_file'], args)
            fix_html(
                args.html_file, 
                args.authors_file,
                args.bib_file,
                args.template_file,
                args.output_file)
        case _:
            abort_if_missing(['authors_file', 'html_file', 'bib_file', 'output_file'], args)
            download_bibs(args.authors_file)
            filter_bibs(
                args.authors_file, 
                args.first_year, 
                args.last_year, 
                args.bib_file)
            generate_html(
                args.bib_file, 
                args.citeproc_executable,
                args.html_file)
            fix_html(
                args.html_file, 
                args.authors_file,
                args.bib_file,
                args.template_file,
                args.output_file)
    print("Thanks!")

