from collections import namedtuple
import re
from xml.etree import ElementTree

import pkg_resources

class Context:
    def __init__(self, elem, lang_id, manager, compile_regex_elem):
        self.elem = elem
        self.manager = manager
        self.style_ref = elem.get('style-ref')
        if self.style_ref is not None and ':' not in self.style_ref:
            self.style_ref = lang_id + ':' + self.style_ref
        self._compile_regex_elem = compile_regex_elem

class SimpleContext(Context):
    def __init__(self, elem, lang_id, manager, compile_regex_elem):
        Context.__init__(self, elem, lang_id, manager, compile_regex_elem)

        self._match_elem = elem.find('match')
        assert self._match_elem is not None
        self._re = None

    def match(self, text):
        if self._re is None:
            self._re = self._compile_regex_elem(self._match_elem)
        m = self._re.match(text)
        if not m:
            return [], text

        match_text = m.group(0)
        return [(self, match_text)], text[len(match_text):]

class ContainerContext(Context):
    def __init__(self, elem, lang_id, manager, compile_regex_elem, children):
        Context.__init__(self, elem, lang_id, manager, compile_regex_elem)
        self._compile_regex_elem = compile_regex_elem
        self._start_re, self._end_re = None, None

        self.start_elem = elem.find('start')
        self.end_elem = elem.find('end')
        self.children = children

    def match(self, text):
        return [], text

class SubPatternContext(Context):
    def __init__(self, elem, lang_id, manager, compile_regex_elem):
        Context.__init__(self, elem, lang_id, manager, compile_regex_elem)

class KeywordContext(Context):
    def __init__(self, elem, lang_id, manager, compile_regex_elem):
        Context.__init__(self, elem, lang_id, manager, compile_regex_elem)

class ReferenceContext(Context):
    def __init__(self, elem, lang_id, manager, compile_regex_elem):
        Context.__init__(self, elem, lang_id, manager, compile_regex_elem)

Language = namedtuple('Language', 'id name hidden root_context')
Style = namedtuple('Style', 'name map_to')
Regex = namedtuple('Regex', 'regex flags')

FULLY_QUAL_ID_REGEX = re.compile(r'\\%{(?P<lang>[^:}]+):(?P<id>[^:}]+)}')
UNQUAL_ID_REGEX = re.compile(r'\\%\{(?P<id>[^:}]+)\}')

def get_regex_flags(regex_or_match, base_flags=0):
    """Return flags for a regex or match element taking account of any
    attributes set on the element.

    """
    flags = base_flags

    if regex_or_match.get('case-sensitive') == 'true':
        flags &= ~re.IGNORECASE
    elif regex_or_match.get('case-sensitive') == 'false':
        flags |= re.IGNORECASE
    elif regex_or_match.get('extended') == 'true':
        flags |= re.VERBOSE
    elif regex_or_match.get('extended') == 'false':
        flags &= ~re.VERBOSE

    # TODO: dupnames
    return flags

def parse_language_tree(tree, manager):
    # pylint: disable=too-many-locals

    # Parse basic language information
    language = tree.getroot()
    assert language.tag == 'language'
    assert language.get('version') == '2.0'

    lang_id = language.get('id')
    assert lang_id is not None

    name = language.get('name') or language.get('_name')
    assert name is not None

    hidden = language.get('hidden') == 'true'

    # Parse styles
    for style in language.iterfind('./styles/style'):
        manager.add_style(
            lang_id, style.get('id'),
            style.get('name') or style.get('_name'), style.get('map-to'))

    # Handle the keyword-char-class element if present
    opening_delimiter, closing_delimiter = r'\b', r'\b'
    kw_char_class = language.find('keyword-char-class')
    if kw_char_class is not None:
        cc = kw_char_class.text
        opening_delimiter = r'(?<!{0})(?={0})'.format(cc)
        closing_delimiter = r'(?<={0})(?!{0})'.format(cc)

    # Default regex flags.
    regex_flags = 0
    dro = language.find('default-regex-options')
    if dro is not None:
        # TODO: implement "dupnames"
        if dro.get('case-sensitive') == 'false':
            regex_flags |= re.IGNORECASE
        if dro.get('extended') == 'true':
            regex_flags |= re.VERBOSE

    # Register each define-regex which has an id attribute with the language
    # manager
    for regex_elem in language.iterfind('./definitions//define-regex[@id]'):
        regex = regex_elem.text or ''
        flags = get_regex_flags(regex_elem, regex_flags)

        # Handle word boundary substitutions
        regex = regex.replace(r'\%[', opening_delimiter)
        regex = regex.replace(r'\%]', closing_delimiter)
        manager.add_regex(
            lang_id, regex_elem.get('id'), regex, flags)

    # A specialised function for the language which will compile a regular
    # expression contained within an element. The element's case-sensitive and
    # extended attributes are respected and the language's default regex options
    # are combined with it. Word boundary and regex references are expanded
    # using the language manager.
    def compile_regex_elem(elem):
        regex = elem.text or ''
        regex = regex.replace(r'\%[', opening_delimiter)
        regex = regex.replace(r'\%]', closing_delimiter)

        # Fully qualify any '\%{id}' references
        regex = UNQUAL_ID_REGEX.sub(r'\%{' + lang_id + r':\1}', regex)

        # Handle any ID references
        while True:
            m = FULLY_QUAL_ID_REGEX.search(regex)
            if not m:
                break
            regex = FULLY_QUAL_ID_REGEX.sub(
                manager.get_regex(m.group('lang') + ':' + m.group('id')),
                regex, count=1
            )

        flags = get_regex_flags(elem, regex_flags)
        return re.compile(regex, flags)

    # Parse each context at the top-level
    lang_context = None
    for context_elem in language.iterfind('./definitions/context'):
        assert context_elem.get('sub-pattern') is None
        context = parse_context(
            context_elem, lang_id, manager, compile_regex_elem)
        context_id = context_elem.get('id')

        if context_id == lang_id:
            lang_context = context

        # Register each context element which has an id attribute
        if context_id is not None:
            manager.add_context(lang_id, context_id, context)

    return Language(lang_id, name, hidden, lang_context)

def parse_context(context_elem, lang_id, manager, compile_regex_elem):
    # Is this a reference context?
    if context_elem.get('ref') is not None:
        return ReferenceContext(
            context_elem, lang_id, manager, compile_regex_elem)

    # Is this a keyword context?
    if context_elem.find('keyword') is not None:
        return KeywordContext(
            context_elem, lang_id, manager, compile_regex_elem)

    # Is this a simple context?
    if context_elem.find('match') is not None:
        return SimpleContext(context_elem, lang_id, manager, compile_regex_elem)

    # Is this a sub-pattern context?
    if context_elem.get('sub-pattern') is not None:
        return SubPatternContext(
            context_elem, lang_id, manager, compile_regex_elem)

    # This is a container
    children = [
        parse_context(child, lang_id, manager, compile_regex_elem)
        for child in context_elem.iterfind('./include/context')
    ]
    return ContainerContext(
        context_elem, lang_id, manager, compile_regex_elem, children)

class LanguageManager:
    def __init__(self):
        self.styles = {}
        self.regexs = {}
        self.contexts = {}
        self._load_builtins()

    def _load_builtins(self):
        for lang_file in pkg_resources.resource_listdir(__name__, 'lang'):
            if not lang_file.endswith('.lang'):
                continue

            with pkg_resources.resource_stream(__name__, 'lang/' + lang_file) as f:
                parse_language_tree(ElementTree.parse(f), self)

    def add_style(self, lang_id, style_id, name, map_to):
        full_id = lang_id + ':' + style_id
        if map_to is None:
            map_to = full_id
        self.styles[full_id] = Style(name, map_to)

    def add_regex(self, lang_id, regex_id, regex, flags):
        full_id = lang_id + ':' + regex_id

        if regex.startswith('/'):
            raise NotImplementedError()

        # Fully qualify any '\%{id}' references
        regex = UNQUAL_ID_REGEX.sub(r'\%{' + lang_id + r':\1}', regex)

        self.regexs[full_id] = Regex(regex, flags)

    def add_context(self, lang_id, ctx_id, ctx):
        full_id = lang_id + ':' + ctx_id
        self.contexts[full_id] = ctx

LANGUAGE_MANAGER = LanguageManager()

def tool():
    import os
    import sys
    from docopt import docopt

    opts = docopt("""
Usage:
    {prog} <source>
    """.format(prog=os.path.basename(sys.argv[0])))

    with open(opts['<source>']) as f:
        for line in f:
            pass
