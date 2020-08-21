from __future__ import print_function, division

from datetime import datetime
#from elasticsearch_dsl import DocType, Text, Date, Integer, Q
import elasticsearch_dsl as es
from elasticsearch_dsl.connections import connections
from elasticsearch.exceptions import NotFoundError
import os, sys
from utils import err, shell
from optparse import OptionParser
from functools import reduce

#indexName = 'howtosv6'
indexName = 'howtos'
indexType = 'howto'
class Howto(es.Document):
    name = es.Text(fields={'raw': es.Keyword()})
    keywords = es.Text(fields={'raw': es.Keyword()})
    hId = es.Text(fields={'keyword': es.Keyword()})
    files = es.Text(fields={'keyword': es.Keyword()})
    rstTime = es.Date()
    htmlTime = es.Date()
    markdownTime = es.Date()
    twikiTime = es.Date()
    pdfTime = es.Date()
    rst = es.Text(analyzer='standard')
    html = es.Text(index=False)
    markdown = es.Text(index=False)
    twiki = es.Text(index=False)
    pdf = es.Text(index=False)
    chars = es.Integer()
    creator = es.Text()
    lastUpdater = es.Text()
    private = es.Boolean()

    class Index:
        name = indexName
        doc_type = indexType

    class Meta:
        doc_type = indexType

    def save(self, **kwargs):
        self.chars = len(self.rst.split())
        self.rstTime = datetime.now()
        return super(Howto, self).save(**kwargs)

    def getHtml(self):
        if (self.rstTime > sef.htmlTime) or (not self.html):
            # rst2html
            pass
        return self.html

    @staticmethod
    def exists():
        return es.Index(indexName).exists()


class ElasticIface(object):

    def __init__(self, verb=False):
        # Define a default Elasticsearch client
        connections.create_connection(hosts=['gaer0012', 'pcaepuppet'])
        self.verb = verb
        self.created = Howto.exists()


    def initIndex(self):
        # Create the mappings in elasticsearch
        Howto.init()
        self.created = True


    def newHowto(self, name, keywords, rst, hId, author=None):
        howto = Howto(name=name, keywords=keywords, hId=hId, rst=rst, creator=author, lastUpdater=author, 
                      private=False, files=[])
        howto.save()
        return howto.meta.id


    def showAll(self, size=None):
        s = Howto.search()
        s = s.sort('name.raw')
        if size: 
            s = s.params(size=size)
            results = s.execute()
        else:
            results = s.scan()

        for howto in results:
            print('name:', howto.name)
            print('_id:', howto.meta.id)
            print('hId:', howto.hId)
            print('files:', howto.files)
            print('rst:', howto.rst.split('\n')[0])
            print('rstTime:', howto.rstTime)
            print('kwords:', howto.keywords)
            print('html:', howto.html.split('\n')[0])
            print('chars:', howto.chars)
            print()


    def getHowto(self, id):
        try:
            return Howto.get(id=id)
        except NotFoundError:
            return None


    def getHowtoHId(self, hId):
        s = Howto.search()
        s = s.query(es.Q({'regexp': {'hId.keyword': hId}}))
        res = s.execute()
        if len(res) == 1:
            return res[0]
        elif len(res)>1 : 
            raise Exception('Unexpected! More than one HowTo maching!')
        else:
            return None


    def getHowtoList(self, idList):
        if not idList:  return []
        return Howto.mget(idList, missing='skip')

#        res = []
#        for id in idList:
#            try:
#                res.append(Howto.get(id=id))
#            except:
#                pass
#
#        return res


    def getHowtoByName(self, name):
        s = Howto.search()
        s = s.query(es.Q({'match': {'name.raw': name}}))
        res = s.execute()
        if len(res) == 1:
            return res[0]
        elif len(res)>1 : 
            raise Exception('Unexpected! More than one HowTo maching!')
        else:
            return None


    def deleteHowto(self, id):
        doc = Howto.get(id=id)
        doc.delete()


    def filter(self, names=[], kwords=[], contents=[], op='$or', 
               Nnames=[], Nkwords=[], Ncontents=[], sortKey='name.raw'):
        """ 
        Returns the records matching both the passed name/kword/contents *lists of*
        patterns. 

        The default operation is to 'and' the filters, but you can 'or' them, passing
        'op=$or' (maybe other operations are possible, but do not rely on it).

        The 'N*' patterns are joined to the others always with 'and' but with a logical
        negation (prefixed with '~').

        If no pattern is set at all, then we return everything. If an incorrect 'op' is
        passed, we raise an exception.
        """     
        # If no specific title filter was passed and operation is OR, then kwords filter
        # is applied to titles also
        if (not names) and kwords and (op == '$or'):  
            names = kwords

        queries = []
#        for name in names:        queries.append(es.Q({'regexp': {'name.raw': '.*'+name+'.*'}}))
        for name in names:        queries.append(es.Q('match', name=name))
        for kword in kwords:      queries.append(es.Q({'regexp': {'keywords.raw': '.*'+kword+'.*'}}))
#        for kword in kwords:      queries.append(es.Q('match', keywords=kword))
        for content in contents:  queries.append(es.Q('match', rst=content))

        Nqueries = []
        for name in Nnames:        Nqueries.append(~es.Q({'regexp': {'name.raw': '.*'+name+'.*'}}))
        for kword in Nkwords:      Nqueries.append(~es.Q('regexp', keywords='.*'+kword+'.*'))
        for content in Ncontents:  Nqueries.append(~es.Q('match', rst=content))
            
        if op == '$and':    myfunc = lambda x,y: x & y
        elif op == '$or':   myfunc = lambda x,y: x | y
        else:  raise Exception('Filter operation not supported')       

#        print(queries)
#        print(Nqueries)
#        print(myfunc)

        s = Howto.search()
        s = s.sort(sortKey)
        s = s.params(size=500)

        expr = Nexpr = None
        if queries:   
            expr  = reduce(myfunc, queries)

        if Nqueries:  
            Nexpr = reduce(lambda x,y: x & y, Nqueries)
            if expr:  expr = expr & Nexpr
            else:     expr = Nexpr

        if expr:  s = s.query(expr)
        
        return s.execute()


    def nameFilter(self, pattern):
        """
        Returns the records matching the passed pattern howto names. 
        """
        return self.filter(names=[pattern])


    def kwordFilter(self, pattern):
        """
        Returns the records matching the passed keyword pattern. 
        """
        return self.filter(kwords=[pattern])


    def contentsFilter(self, pattern):
        """
        Returns the records matching the passed keyword pattern. 
        """
        return self.filter(contents=[pattern])


    def update(self, id, changes, version=None):
        """
        Updates record with specified 'id' by applying specified 'changes' (dict with
        modified fields).

        If 'version' is specified, then ES will complain if the DB version is higher than 
        that supplied and the operation will fail.
        """
        howto = Howto.get(id=id)

        if version:  howto.meta.version = version

        howto.update(**changes)


    def parseDir(self, dir):
        """
        Parse howto files in <dir>/data and generate the collection of howtos with 'name',
        'fname', and basic list of keywords (hyphen-separated tokens in name).
        """
        # Create index and necessary mappings
        if not self.created:  self.initIndex()

        hDir = dir + '/data'
        fnames = os.listdir(hDir)

        for fname in fnames:

            if not fname.startswith('howto-'):  continue
            if self.verb:  print('Processing file %s' % fname)

            tokens = fname.split('.rst')[0].split('-')[1:]
            name = '-'.join(tokens)
#            hMap['fname'] = fname
            kwords = tokens

            f = open(hDir+'/'+fname)
            rst = f.read()

            # We insert using Unicode, however, we first need to decode the original
            # files, we try with UTF-8, but if that fails, then we try with latin-1...
            # else, we fail for good
            try:
                rst = unicode(rst, encoding='utf-8')
            except UnicodeDecodeError as inst:
                rst = unicode(rst, encoding='latin-1')

            f.close()

            # Insert into ElasticSearch
            self.newHowto(name, tokens, rst)

        return 0


    def rereadFromFiles(self, dir='/var/www/html/howtos/'):
        """
        Delete existing ES howto index and create it again using howto files under
        specified directory.
        """

        # If it existed, remove it
        if self.created:  
            print("Deleting existing ES index")
            howtos = es.Index('howtos')
            howtos.delete()
            self.created = False

        # Now, create it from files again
        self.parseDir(dir)

        return 0


# showAll()


def main():
    """
     Performes the main task of the script (invoked directly).
     For information on its functionality, please call the help function.
    """
    
    # Options
    helpstr = """%prog [options]

Interface for Elasticsearch HowTos service.

The idea is to use this more like a library (from a python program) but limited
functionality is also available as a script."""

    # Create parser with general help information
    parser = OptionParser(usage=helpstr, version="%prog-2.0")

    # Option verbose ('store_true' option type)
    helpstr = "Be verbose (show additional information)"
    parser.add_option("-v", "--verbose", dest="verb", help=helpstr, action="store_true")

    # Option usage 
    helpstr = "Show usage information"
    def myusage(option, opt, value, parser): 
        print(parser.get_usage().split('\n')[0])
        sys.exit(0)
    parser.add_option("-u", "--usage", help=helpstr, action="callback",  
                      callback=myusage)
    def usage():
        print(parser.get_usage().split('\n')[0])

    helpstr = """Use 'dir' as the base for HowTo files (probabl, for parsing)."""
    parser.add_option("-d", "--dir", dest="dir", help=helpstr, 
                      action="store", default='/var/www/html/howtos/')

    helpstr = "Delete existing ES howto index and create it again using howto files"
    parser.add_option("--reread", dest="reread", help=helpstr, action="store_true")

    # Do parse options
    (opts, args) = parser.parse_args()

    # Shortcut for verbose
    verb = opts.verb

    
    #### REAL MAIN ####
    if opts.reread:
        db = ElasticIface(verb=True)
        db.rereadFromFiles(opts.dir)
    
    
    # Exit successfully
    return 0


###    SCRIPT    ####
if __name__=="__main__":
    sys.exit(main())
