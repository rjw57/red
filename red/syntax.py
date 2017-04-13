import re
from xml.etree import ElementTree

import pkg_resources

STYLES = {}
REGEXES = {}
CONTEXTS = {}
LANG_ROOT_CONTEXTS = {}

def parse_lang(file_object):
    tree = ElementTree.parse(file_object)
    prefix = tree.get('id')

    styles = tree.find('styles')
    if styles is not None:
        for style in styles.iterfind('style'):
            map_to = style.get('map-to', style.get('id'))
            STYLES[prefix + ':' + style.get('id')] = map_to

    definitions = tree.find('definitions')
    if definitions is not None:
        for regex in definitions.iterfind('define-regex'):
            re_text = regex.text if regex.text is not None else ''
            REGEXES[prefix + ':' + regex.get('id')] = re.compile(re_text)
        for context in definitions.iterfind('context'):
            ctx = None # TODO parse
            CONTEXTS[prefix + ':' + context.get('id')] = ctx

    LANG_ROOT_CONTEXTS = prefix + ':' + prefix

def _parse_builtin_langs():
    for lang_file in pkg_resources.resource_listdir(__name__, 'lang'):
        if not lang_file.endswith('.lang'):
            continue

        with pkg_resources.resource_stream(__name__, 'lang/' + lang_file) as f:
            parse_lang(f)

def lex(text):
    return [None] * len(text)
