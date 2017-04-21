import re
import collections
from xml.etree import ElementTree

import pkg_resources

# Dictionaries mapping ids to elements. Ids are always in the format
# "<lang>:<id>". Additionally we set the "_lang" attribute on all elements to
# the id of the language they were extracted from. This aids in resolving
# unqualified refs.
STYLE_BY_ID = {}
REGEX_BY_ID = {}
CONTEXT_BY_ID = {}

# Dictionary giving the root context for each language
LANG_ROOT_CONTEXT = {}

def parse_lang(file_object):
    # pylint: disable=no-member
    tree = ElementTree.parse(file_object)
    prefix = tree.getroot().get('id')
    hidden = tree.getroot().get('hidden', 'false') == 'true'

    styles = tree.find('styles')
    if styles is not None:
        for style in styles.iterfind('style'):
            style.set('_lang', prefix)
            STYLE_BY_ID[prefix + ':' + style.get('id')] = style

    definitions = tree.find('definitions')
    if definitions is not None:
        # Note we look at *all* sub elements here since regexs can be defined
        # inside certain <context> elemenrs.
        for regex in definitions.iter('define-regex'):
            regex.set('_lang', prefix)
            if regex.get('id') is None:
                continue
            REGEX_BY_ID[prefix + ':' + regex.get('id')] = regex
        # The same for contexts
        for context in definitions.iter('context'):
            context.set('_lang', prefix)
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

# The evaluation context for matching. We have the concept of the "current"
# context which is the context to match. If matching fails, we have a "default"
# context which should be tried.
LexState = collections.namedtuple(
    'LexState', 'context def_context')

# The result of attempting to match a context. Next context may be None if the
# default context should be tried.
MatchResult = collections.namedtuple(
    'MatchResult', 'match_text style next_context')

def _match_context(context, text):
    """Match text to the passed context. If there is a match, return the match
    text otherwise return None.

    """
    ref = context.get('ref')
    if ref is not None:
        return _match_ref_context(context, text)

    include = context.find('include')

    if include is not None:
        # Context is a reference context, process each context in turn until it
        # matches.
        for sub_context in include.iterfind('context'):
            m = _match_context(sub_context, text)
            if m is not None:
                return m

    return None

def _match_ref_context(context, text):
    ref = context.get('ref')
    prefix = context.get('_lang')

    if ref.endswith(':*'):
        for id_, c in CONTEXT_BY_ID.iteritems():
            if not id_.startswith(prefix + ':'):
                continue
            m = _match_context(c, text)
            if m is not None:
                return m
        return None

    if ':' not in ref:
        ref = prefix + ':' + ref

    return _match_context(CONTEXT_BY_ID[ref], text)

def start_lang(lang):
    ctx = LANG_ROOT_CONTEXT[lang]
    return LexState(ctx, ctx)

def lex(text, state):
    rv = []

    while len(text) > 0:
        ctx = state.context
        assert ctx is not None

        match = _match_context(ctx, text)
        if match is not None:
            text = text[len(match):]
            style = ctx.get('style-ref', 'foo')
            rv.extend([style] * len(match))
            state = LexState(state.def_context, state.def_context)
        else:
            rv.append(None)
            text = text[1:]
            state = LexState(state.def_context, state.def_context)

    return rv, state
