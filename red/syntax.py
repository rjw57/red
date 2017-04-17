import re
import collections
from xml.etree import ElementTree

import pkg_resources

# Dictionaries mapping ids to elements. Ids are always in the format
# "<lang>:<id>".
STYLE_BY_ID = {}
REGEX_BY_ID = {}
CONTEXT_BY_ID = {}

# Dictionary giving the root context for each language
LANG_ROOT_CONTEXT = {}

def parse_lang(file_object):
    tree = ElementTree.parse(file_object)
    prefix = tree.getroot().get('id')
    hidden = tree.getroot().get('hidden', 'false') == 'true'

    styles = tree.find('styles')
    if styles is not None:
        for style in styles.iterfind('style'):
            STYLE_BY_ID[prefix + ':' + style.get('id')] = style

    definitions = tree.find('definitions')
    if definitions is not None:
        # Note we look at *all* sub elements here since regexs can be defined
        # inside certain <context> elemenrs.
        for regex in definitions.iter('define-regex'):
            if regex.get('id') is None:
                continue
            REGEX_BY_ID[prefix + ':' + regex.get('id')] = regex
        # The same for contexts
        for context in definitions.iter('context'):
            if context.get('id') is None:
                continue
            CONTEXT_BY_ID[prefix + ':' + context.get('id')] = context

    if not hidden:
        LANG_ROOT_CONTEXT[prefix] = CONTEXT_BY_ID[prefix + ':' + prefix]

def _parse_builtin_langs():
    for lang_file in pkg_resources.resource_listdir(__name__, 'lang'):
        if not lang_file.endswith('.lang'):
            continue

        with pkg_resources.resource_stream(__name__, 'lang/' + lang_file) as f:
            parse_lang(f)

_parse_builtin_langs()

EvalResult = collections.namedtuple(
    'EvalResult', 'match_text style next_context tail_text')

LexState = collections.namedtuple(
    'LexState', 'context root_context')

def _evaluate_context(context, text):
    include = context.find('include')

    if include is not None:
        # Context is a reference context, process each context in turn until it
        # matches.
        for context in include.iterfind('context'):
            pass

    return EvalResult(text, None, context, '')

def start_lang(lang):
    ctx = LANG_ROOT_CONTEXT[lang]
    return ctx

def lex(text, state):
    rv = []

    while len(text) > 0:
        match = _evaluate_context(state, text)
        if match is not None:
            match_text, style, state, text = match
            rv.extend([style] * len(match_text))
        else:
            rv.extend([None] * len(text))
            text = ''

    return rv, state
