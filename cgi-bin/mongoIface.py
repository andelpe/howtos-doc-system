import warnings
warnings.simplefilter('ignore', DeprecationWarning)
import sys, os, time
import json
import pickle
from optparse import OptionParser
import pymongo as m


def err(msg):
    """
    Prints the specified string msg to standard error (with an added trailing newline)
    """
    sys.stderr.write(msg + '\n')


class mongoIface:
    """
    MongoDB interface object for the HowTos.
    """

    def __init__(self, verb = False):
        """
        Constructor. Get pointer to the howtos list data collection.
        """
        client = m.MongoClient()
        db = client.howtos
        self.list = db.list
        self.verb = verb


    def filter(self, name, kword):
        """
        Returns the records matching both the passed name and kword patterns. 
        """
        andedList = []

        if name:
            if type(name) == list:
                for elem in name:  
                    if elem:  andedList.append({'name': {'$regex': elem}})
            else:  andedList.append({'name': {'$regex': name}})

        if kword:
            if type(kword) == list:
                for elem in kword:  
                    if elem:  andedList.append({'kwords': {'$elemMatch': {'$regex': elem}}})
            else:  andedList.append({'kwords': {'$elemMatch': {'$regex': kword}}})

        if andedList:  return self.list.find({'$and': andedList})
        else:          return self.list.find()

#        f = open('/tmp/debug', 'w')
#        f.write(str(andedList))
#        f.close()


    def nameFilter(self, pattern):
        """
        Returns the records matching the passed pattern howto names. 
        """
        return self.list.find({'name': {'$regex': pattern}})


    def kwordFilter(self, pattern):
        """
        Returns the records matching the passed keyword pattern. 
        """
        return self.list.find({'kwords': {'$elemMatch': {'$regex': pattern}}})


    def parseDir(self, dir):
        """
        Parse howto files in <dir>/data and generate the collection of howtos with 'name',
        'fname', and basic list of keywords (hyphen-separated tokens in name).
        """
        hDir = dir + '/data'
        fnames = os.listdir(hDir)

        all = []
        for fname in fnames:

            hMap = {}
            if not fname.startswith('howto-'):  continue
            if self.verb:  print 'Processing file %s' % fname

            tokens = fname.split('.rst')[0].split('-')[1:]
            hMap['name'] = fname
            hMap['fname'] = fname
            hMap['kwords'] = tokens

            all.append(hMap)

        self.list.insert(all)
        return 0


if __name__ == '__main__':

    helpstr = """%prog <pattern>
This is meant to be used as a module for interfacing the HowTos mongo database. 

As a script it can be used to test some functionalities. Please provide a pattern to
filter howto entries in the DB."""

    parser = OptionParser(usage=helpstr, version='%prog-1.0')
    opts, args = parser.parse_args()

    if len(args) != 1:
        parser.error('Incorrect number of arguments')

    # Initialize 
    ifc = mongoIface()

    # Tests
    print '\nTest name pattern matching:'
    for row in ifc.nameFilter(args[0]):
        print '  %s --> %s' % (row['name'], row['kwords'])

    print '\nTest keywords pattern matching:'
    for row in ifc.kwordFilter(args[0]):
        print '  %s --> %s' % (row['name'], row['kwords'])

    print '\nTest general filter:'
    for row in ifc.kwordFilter('cms', args[0]):
        print '  %s --> %s' % (row['name'], row['kwords'])

    print
