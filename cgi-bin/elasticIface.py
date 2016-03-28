from datetime import datetime
#from elasticsearch_dsl import DocType, String, Date, Integer, Q
import elasticsearch_dsl as es
from elasticsearch_dsl.connections import connections
import os, sys
from utils import err, shell
from optparse import OptionParser

indexName = 'howtos'
class Howto(es.DocType):
    name = es.String(fields={'raw': es.String(index='not_analyzed')})
    keywords = es.String(index='not_analyzed')
    rstTime = es.Date()
    htmlTime = es.Date()
    twikiTime = es.Date()
    pdfTime = es.Date()
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
        return es.Index(indexName).exists()


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
        for name in names:        queries.append(es.Q('regexp', name='.*'+name+'.*'))
        for kword in kwords:      queries.append(es.Q('regexp', keywords='.*'+kword+'.*'))
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


    def rereadFromFiles(self, dir='/var/www/html/howtos/'):
        """
        Delete existing ES howto index and create it again using howto files under
        specified directory.
        """

        # If it existed, remove it
        if self.created:  
            print "Deleting existing ES index"
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
        print parser.get_usage().split('\n')[0]
        sys.exit(0)
    parser.add_option("-u", "--usage", help=helpstr, action="callback",  
                      callback=myusage)
    def usage():
        print parser.get_usage().split('\n')[0]

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