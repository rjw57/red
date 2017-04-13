import re
from xml.etree import ElementTree

TOK_KEYWORD = 'keyword'
TOK_NORMAL = 'normal'

class LanguageLexer:
    def __init__(self):
        self._styles = {}
        self._regexs = {}
        self._contexts = {}
        self._root_context_id = None

    def read_spec(self, file_object, prefix):
        tree = ElementTree.parse(file_object)

        styles = tree.find('styles')
        if styles is not None:
            for style in styles.iterfind('style'):
                map_to = style.get('map-to', style.get('id'))
                self._styles[prefix + ':' + style.get('id')] = map_to

        definitions = tree.find('definitions')
        if definitions is not None:
            for regex in definitions.iterfind('define-regex'):
                re_text = regex.text if regex.text is not None else ''
                self._regexs[prefix + ':' + regex.get('id')] = re.compile(re_text)
            for context in definitions.iterfind('context'):
                ctx = self._parse_context(context, prefix)
                self._contexts[prefix + ':' + context.get('id')] = ctx

        self._root_context_id = prefix + ':' + prefix

    def _parse_context(self, context, prefix):
        pass

    def lex(self, text):
        if self._root_context_id is None:
            return [TOK_NORMAL] * len(text)

        context = self._contexts[self._root_context_id]

        return [TOK_NORMAL] * len(text)
