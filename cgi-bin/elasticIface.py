from datetime import datetime
#from elasticsearch_dsl import DocType, String, Date, Integer, Q
import elasticsearch_dsl as es
from elasticsearch_dsl.connections import connections
import os

indexName = 'howtos'
class Howto(es.DocType):
    name = es.String(fields={'raw': es.String(index='not_analyzed')})
    keywords = es.String(index='not_analyzed')
    rstTime = es.Date()
    htmlTime = es.Date()
    rst = es.String(analyzer='snowball')
    html = es.String(index='no')
    chars = es.Integer()

    class Meta:
        index = indexName

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
        es.Index(indexName).exists()


class ElasticIface(object):

    def __init__(self, verb=False):
        # Define a default Elasticsearch client
        connections.create_connection(hosts=['localhost'])
        self.verb = verb
        self.created = Howto.exists()

    def initIndex(self):
        # Create the mappings in elasticsearch
        Howto.init()
        self.created = True


    def newHowto(self, name, keywords, rst):
        howto = Howto(name=name, keywords=keywords, rst=rst)
        howto.save()


    def showAll(self, size=None):
        s = Howto.search()
        s = s.sort('name.raw')
        if size: 
            s = s.params(size=size)
            results = s.execute()
        else:
            results = s.scan()

        for howto in results:
            print 'name:', howto.name
            print '_id:', howto.meta.id
            print 'rst:', howto.rst.split('\n')[0]
            print 'rstTime:', howto.rstTime
            print 'kwords:', howto.keywords
            print 'html:', howto.html.split('\n')[0]
            print 'chars:', howto.chars
            print

    def getHowto(self, id):
        return Howto.get(id=id)


    def filter(self, names=[], kwords=[], contents=[], op='$and'):
        """ 
        Returns the records matching both the passed name/kword/contents *lists of*
        patterns. 

        The default operation is to 'and' the filters, but you can 'or' them, passing
        'op=$or' (maybe other operations are possible, but do not rely on it).

        If no pattern is set at all, then we return everything. If an incorrect 'op' is
        passed, we raise an exception.
        """     
        queries = []
        for name in names:        queries.append(es.Q('regexp', name=name))
        for kword in kwords:      queries.append(es.Q('regexp', keywords=kword))
        for content in contents:  queries.append(es.Q('match', rst=content))
            
        if op == '$and':    myfunc = lambda x,y: x & y
        elif op == '$or':   myfunc = lambda x,y: x | y
        else:  raise Exception('Filter operation not supported')       

#        print queries
#        print myfunc

        s = Howto.search()
        s = s.sort('name.raw')
        s = s.params(size=100)
        if queries:  s = s.query(reduce(myfunc, queries))
        
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


    def update(self, id, changes):
        """
        Updates record with specified 'id' by applying specified 'changes' (dict with
        modified fields).
        """
        howto = Howto.get(id=id)
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
            if self.verb:  print 'Processing file %s' % fname

            tokens = fname.split('.rst')[0].split('-')[1:]
            name = '-'.join(tokens)
#            hMap['fname'] = fname
            kwords = tokens

            f = open(hDir+'/'+fname)
            rst = f.read().decode("latin-1").encode("utf-8")
            f.close()

            # Insert into ElasticSearch
            self.newHowto(name, tokens, rst)

        return 0

# showAll()
