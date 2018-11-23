#!/usr/bin/env python

#from __future__ import division, print_function

# We maintain a structure of most-accessed Docs (basically a priority queue) and a similar
# one for most-accessed keywords (series of priority queues) in Redis.
#
# In this way, we don't need to query ElasticSearch too much.


#
# TODO: support the version checking in web edition also?
#       It's not easy, because we may save many times in the web, each will have a new version num!
#
# TODO: add a different list view, with columns, so that we can e.g. sort by creation/modif time
#

### IMPORTS ###
import os, logging, time
import re
import subprocess as sub
import cgi
from elasticIface import ElasticIface
import bson
from utils import shell, commandError
from datetime import datetime
import json
import redis
from fixcols import fixcols


### CONSTANTS ####
configFile = '/etc/howtos.json'
BASEDIR = '/var/www/html/howto'
CGIDIR = '/var/www/cgi-bin/howtos'
howtoDir = os.path.join(BASEDIR, 'data')
newDir = os.path.join(BASEDIR, 'new')
privateHowtos = os.path.join(howtoDir, '.private')

REDIS_SOCKET = '/run/redis/redis.sock'

rst2html = CGIDIR + '/txt2html/command3.sh'
rst2twiki = CGIDIR + '/rst2twiki'
rst2mdown = CGIDIR + '/rst2mdown'
mdown2rst = CGIDIR + '/mdown2rst'
rst2pdf = CGIDIR + '/txt2pdf/command3.sh'

ERROR_PAGE = os.path.join(BASEDIR, 'error.html')
EXISTING_PAGE = os.path.join(BASEDIR, 'existing.html')

BASE_CONTENTS = """%(title)s
%(sub)s

.. contents:: Table of Contents
.. sectnum::


"""

numCommon = 12
numRecent = 12
#maxRecent = numRecent**2
numKwords = 15

QuickFilterKeys = ('ops', 'dcache', 'monitor', 'htcondor', 'network',)
QuickFilterNKeys = ('ops',)

linkFormat = "^[a-zA-Z0-9._\-]*$"
linkPattern = re.compile(linkFormat)


### FUNCTIONS ####


### CLASSES ###
class howtos(object):

    def __init__(self, logfile='/var/log/howtos'):
        """
        Constructor. Create the list of private pages.
        """
        f = open(privateHowtos)
        lines = f.readlines()
        f.close()
        self.privatePages = [x.strip() for x in lines]

# Pre-loading things is not very effective is the script is called anew each time
# We were actually reading files we were often not using...

        # Prepare logfile
        self.mylogf = open(logfile, 'a')

        # Default config
        self.c = {
            'readOnly': False,
            'showTempl': os.path.join(BASEDIR, 'show.templ'),
            'iniTempl':  os.path.join(BASEDIR, 'ini.templ'),
            'editTempl': os.path.join(BASEDIR, 'edit.templ'),
            'delTempl': os.path.join(BASEDIR, 'deleted.templ'),
            'updateKTempl': os.path.join(BASEDIR, 'updateK.templ')
        }
        # Update with whatever is in the config file
        try:
            fconf = open(configFile)
            self.c.update(json.load(fconf))
        except Exception, inst:
            if os.path.isfile(configFile):
                self.mylogf.write('%s WARNING: could not load config file %s: %s\n' 
                        % (time.strftime('%Y-%m-%d %H:%M:%S'), configFile, inst))
        
        # Update some settings based on the config
        if self.c['readOnly']:

            def prependRO(f):
                return os.path.join(os.path.dirname(f), 'RO_' + os.path.basename(f))

            self.c['showTempl'] = prependRO(self.c['showTempl'])
            self.c['iniTempl']  = prependRO(self.c['iniTempl'])
            self.c['editTempl'] = self.c['updateKTempl'] = self.c['delTempl'] = os.path.join(BASEDIR, 'ReadOnlyError.templ')

        # Connect to mongoDB
        self.db = ElasticIface()

        # Connect to redis also
        self.cache = redis.StrictRedis(unix_socket_path=REDIS_SOCKET)


    def loadFile(self, fname):
        """
        Get contents of indicated template file either from disk or some cache.
        """
        # TODO: Cache files content in redis: need some way to update/evict them and fall
        #       back to disk when cached version is not present/old
        with open(fname) as f:
            text = f.read()
        return text


    def mylog(self, msg):
        """
        Log specified message to defined logfile.
        """
        self.mylogf.write('%s %s \n' % (time.strftime('%Y-%m-%d %H:%M:%S'), msg))


    def getCommonDocs(self):
        """
        Asks redis and retrieves the list of 'numCommon' most accessed HowTo docs.
        """
        return self.cache.zrevrange('commonDocs', 0, numCommon-1)


    def getRecentDocs(self):
        """
        Asks redis and retrieves the list of 'numRecent' most recently accesed HowTo docs.
        """
        return self.cache.lrange('recentDocs', 0, numRecent-1)


    def getCommonKwords(self):
        """
        Asks redis and retrieves the list of 'numKwords' most accessed keywords. 
        """
        return self.cache.zrevrange('commonKwords', 0, numKwords)


    def getRecentKwords(self):
        """
        Asks redis and retrieves the list of 'numRecent' most recently accessed keywords.
        """
        return self.cache.lrange('recentKwords', 0, numKwords)


    def getPage(self, docId=None, hId=None, format='html'):
        """
        Get a Howto and return it as text/html/twiki.
        """
        self.mylog("In getPage: %s %s %s" % (docId, hId, format))
        try:
            # Here we get the RST contents from ES, in Unicode type
            # Thus, we'd better encode them before passing to shell for HTML/twiki.. production

            if docId:    
                mypage = self.db.getHowto(docId)
            elif hId: 
                mypage = self.db.getHowtoHId(hId)
                docId = mypage.meta.id
                mypage = self.db.getHowto(docId)
            else: 
                raise Exception('Error in getPage: No id/hId provided')

            if not mypage: return None
#            self.mylog("MYPAGE: %s" % mypage)

            # Add the page to the caches 
            self.cache.lrem('recentDocs', 1, docId)
            self.cache.lpush('recentDocs', docId)
            self.cache.ltrim('recentDocs', 0, numRecent)
            self.cache.zincrby('commonDocs', amount=1, value=docId)
           
            if format in ('md', 'markdown'):

                # Check if Markdown field is there and is up-to-date. If not, produce it and store it
                if ('markdown' not in mypage) or ('markdownTime' not in mypage) or (mypage.markdownTime < mypage.rstTime):
                    out = shell(rst2mdown + ' -', input=mypage.rst.encode('utf-8'))
                    if self.c['readOnly']:
                        mypage.markdown = out
                    else:
                        self.db.update(docId, {'markdown': out, 'markdownTime': datetime.now()})
                        mypage = self.db.getHowto(docId)

            if format == 'html':

                # Check if HTML field is there and is up-to-date. If not, produce it and store it
                if (not mypage.html) or (not mypage.htmlTime) or (mypage.htmlTime < mypage.rstTime):
                    out = shell(rst2html + ' -', input=mypage.rst.encode('utf-8'))
                    if self.c['readOnly']:
                        mypage.html = out
                        mypage.htmlTime = datetime.now()
                    else:
                        self.db.update(docId, {'html': out, 'htmlTime': datetime.now()})
                        mypage = self.db.getHowto(docId)

            elif format == 'twiki':

                # Check if Twiki field is there and is up-to-date. If not, produce it and store it
                if ('twiki' not in mypage) or ('twikiTime' not in mypage) or (mypage.twikiTime < mypage.rstTime):
#                    self.mylog("Going into Twiki production")
                    out = shell(rst2twiki + ' -', input=mypage.rst.encode('utf-8'))
                    if self.c['readOnly']:
                        mypage.twiki = out
                    else:
                        self.db.update(docId, {'twiki': out, 'twikiTime': datetime.now()})
                        mypage = self.db.getHowto(docId)

            elif format == 'pdf':

                # Check if PDF field is there and is up-to-date. If not, produce it and store it
                if ('pdf' not in mypage) or ('pdfTime' not in mypage) or (mypage.pdfTime < mypage.rstTime):
                    out = shell(rst2pdf + ' -', input=mypage.rst.encode('utf-8'))
                    self.mylog("PDF produced: %s" % mypage.name)
                    # Apparently PDF is produced in latin-1, so it's easier to store it in DB in latin-1
                    # (otherwise failures happen...). When storing in the DB, we explicitely 
                    # convert to unicode to indicate that latin-1 should be used to decode
                    if self.c['readOnly']:
                        mypage.pdf = unicode(out, encoding='latin-1')
                    else:
                        self.db.update(docId, {'pdf': unicode(out, encoding='latin-1'), 'pdfTime': datetime.now()})
                        self.mylog("....After DB update")
                        mypage = self.db.getHowto(docId)

            # Add the associated keywords to the caches
            for kword in mypage.keywords:
                self.cache.lrem('recentKwords', 1, kword)
                self.cache.lpush('recentKwords', kword)
                self.cache.ltrim('recentKwords', 0, numRecent)
                self.cache.zincrby('commonKwords', amount=1, value=kword)

            # All OK
            return mypage

        except Exception, inst:
            # TODO: Improve this
            self.mylog("EXCEPTION: %s" % inst)
            return None


    def howtoList(self, rows):
        """
        Return HTML lines for the specified list howto docs.
        """
        text = ''
        cont = 0
        for row in rows:
            title = row.name
            docId = row.meta.id
            if (not docId in self.privatePages):
                    mylink = 'href="/howtos?id=%s' % docId
                    if (cont % 4) == 0: text += '\n<tr>'
                    text += '\n<td>'
                    text += '<a class="howtoLink" %s">%s</a>' % (mylink, title)
                    text += '&nbsp;&nbsp;&nbsp;<br/>'
                    linkList = ['<a class="smLink" href="/howtos?kwf=%s">%s</a>' % (x,x) for x in row.keywords]
                    text += ' &nbsp;'.join(linkList)
                    text += '&nbsp;&nbsp;<br/>&nbsp;</td>'
                    if (cont % 4) == 3: text += '\n</tr>' 
                    cont += 1
        text += '\n' # <tr><td colspan="4"><hr></td></tr>'

        return text


    def _getMeta(self, doc, longl=False):
        """
        Produce a json of the passed doc.
        """
        elem = {'name': doc.name, 'id': doc.meta.id, 'kwords': ','.join(doc.keywords)}


        if longl: 
            if not hasattr(doc.meta, 'version'):
                doc = self.db.getHowto(elem['id'])
            elem['version'] = doc.meta.version
            elem['creator'] = doc.creator
            elem['lastUpdater'] = doc.lastUpdater
            elem['rstTime'] = doc.rstTime.strftime('%Y-%m-%d %H:%M')
            if not doc.hId:  elem['hId'] = 'UNASSIGNED'
            else:            elem['hId'] = doc.hId

        return elem
            # Note: it seems that listed doc do not include version info, so we cannot use the following 
#            result.append({'name': row.name, 'id': row.meta.id, 'kwords': ','.join(row.keywords), 'version': row._version})


    def getMeta(self, docId, isHId=False, longl=False):
        """
        Produce a json of the doc with specified id.
        """
        if isHId:  doc = self.db.getHowtoHId(docId)
        else:      doc = self.db.getHowto(docId)

        if doc:  
            elem = self._getMeta(doc, longl)
            print "Content-type: application/json\n" 
            print json.dumps(elem)

        else:    
            print "Status: 400 Bad Request"
            print "Content-type: text/html\n"
            errmsg = "No element matching specified id/hId %s" % docId
            print (errmsg)


    def list(self, rows, longl=False):
        """
        Produce a json list of passed docs.
        """
        result = []
        for row in rows:
            elem = self._getMeta(row, longl)
            result.append(elem)

        print "Content-type: application/json\n" 
        print json.dumps(result)


    def produceIndex(self, rows=None, tf=[], kwf=[], bf=[], filtOp='$and', Nkwf=[]):
        """
        Produce an index page to look for documents.
        """
        baseFilt = "&emsp; &emsp; &emsp; &emsp; &emsp; &emsp;"
        baseFilt += """<input type="radio" name="filtOp" value="$or"  %s>OR</input>"""  % ('checked' if filtOp=='$or' else '')
        baseFilt += """&nbsp;<input type="radio" name="filtOp" value="$and" %s>AND</input>""" % ('checked' if filtOp!='$or' else '')

#        baseKword = """&nbsp;Title/Kword filter: <input type="text" class="filter" name="kwf" value="%s" />"""
#        baseBody  = """&nbsp;&nbsp;&nbsp; Contents filter: <input type="text" class="filter" name="bf" value="%s" />""" 
        baseTitle = """<input type="text" size="20" class="filter" name="tf" value="%s" autofocus >"""
        baseKword = """<input type="text" size="20" class="filter" name="kwf" value="%s" autofocus >"""
        baseBody  = """<input type="text" size="19" class="filter" name="bf" value="%s" >""" 
        
        baseNKword = """<input type="text" size="17" class="Nfilter" name="Nkwf" value="%s" >"""
        
        text = self.loadFile(self.c['iniTempl'])

        def createText(mylist, buttonText, baseText):
            if not mylist:  mylist = [""]
            mytext = """<input class="plusbutton" type="button" value="+" onclick="%s">""" % buttonText
            mytext  += "<br/>\n".join([baseText % elem  for elem in mylist])
            return mytext


        sectionText = '<tr><td colspan="4"><br/><span class="mylabel">%s</span><hr></td></tr>'
        mainList = self.howtoList(rows) if rows!=None else self.howtoList(self.db.filter(tf, kwf, bf))

        commonKwords = self.getCommonKwords()
        if not (tf or kwf or bf):

            mainPart = sectionText % ('All docs') + mainList

            recentPart = sectionText % ('Recently visited')
            recentList = self.db.getHowtoList(self.getRecentDocs())
            rKwds = ['<a class="smLink2" href="/howtos?kwf=%s">%s</a>' % (x,x) for x in self.getRecentKwords()]
            if rKwds:
                recentPart += '<tr><td colspan="4">' + ' &nbsp; '.join(rKwds) + '<br/><hr></td></tr>'
            if recentList:
                recentPart += self.howtoList(recentList)

            commonList = self.db.getHowtoList(self.getCommonDocs())
            commonPart = sectionText % ('Most visited') 
            cKwds = ['<a class="smLink2" href="/howtos?kwf=%s">%s</a>' % (x,x) for x in commonKwords]
            if cKwds:
                commonPart += '<tr><td colspan="4">' + ' &nbsp; '.join(cKwds) + '<br/><hr></td></tr>'
            if commonList:
                commonPart += self.howtoList(commonList)

        else:

            mainPart = sectionText % 'Results' + mainList
            commonPart = recentPart = ""

        commonKwdOpts = ''
        for k in commonKwords:
            commonKwdOpts += '<a onclick="addKword(\'%s\')">%s</a>' % (k, k)

        map = {
            'tf': createText(tf, 'addTf()', baseTitle),
            'kwf': createText(kwf, 'addKwf()', baseKword),
            'Nkwf': createText(Nkwf, 'addNkwf()', baseNKword),
            'bf':  createText(bf, 'addBf()', baseBody),
            'common': commonPart, 'recent': recentPart, 'list': mainPart,
            'baseFilt': baseFilt, 'commonKwords': commonKwdOpts,
        }
        for key in (QuickFilterKeys):
            map['qf_'+key] = str(key in kwf)
        for key in (QuickFilterNKeys):
            map['qf_N_'+key] = str(key in Nkwf)

        return text % map


    def output(self, docId=None, tf=[], kwf=[], bf=[], filtOp=None,
               format='html', action='show', direct=False, longl=False, 
               Nkwf=[], qfClicked="NULL", hId=None):
#               Nkwf=[], quickFilters={}):
        """
        Basic method to display the index page (with appropriate filter) or
        a howto page in the specified format, or the edition page, or even a 
        simple info message.
        """
        self.mylog("In output: %s, %s" % (action, format))

        def sanitizeList(v):
            """
            Return a list based on 'v', be it a list itself, a single string, 
            or one including commas (several elements).
            """
            result = []
            if v and (type(v) == list):
                for item in v:
                    if ',' in item: result += item.split(',')
                    else:           result.append(item)
            elif v:
                result = v.split(',')
            return result

        # Sanitize filters (at least one filter of each, but by default containing nothing)
        tf = sanitizeList(tf)
        kwf = sanitizeList(kwf)
        bf = sanitizeList(bf)

#        self.mylog(Nkwf)
        if (Nkwf == None) and (qfClicked == None):  
            Nkwf = ['ops']
        Nkwf = sanitizeList(Nkwf)

        if not filtOp:  filtOp = '$and'

        if qfClicked and (qfClicked != "NULL"):
            mylist = kwf
            if qfClicked.startswith('N_'):  
                mylist = Nkwf
                qfClicked = qfClicked[2:]
            if qfClicked in mylist:  mylist.remove(qfClicked)
            else:                    mylist.append(qfClicked)

        # If action was list, return json
        if action == 'list':

            # Get matching docs
            rows = self.db.filter(names=tf, kwords=kwf, contents=bf, op=filtOp, Nkwords=Nkwf)

            # Return appropiate json 
            self.list(rows, longl=longl)

        # If no id/hId is given, filter the DB
        elif ((not docId) or (docId == 'index.html')) and (not hId):

            # Get matching docs
            rows = self.db.filter(names=tf, kwords=kwf, contents=bf, op=filtOp, Nkwords=Nkwf)

            # If only one match (and 'direct' flag), show it directly
            if direct and (len(rows) == 1):
                self.show(rows[0], format=format, title=rows[0].name)

            # Else, produce the page showing the complete list
            else:
                self.show(contents=self.produceIndex(rows, tf, kwf, bf, filtOp, 
                                                     Nkwf=Nkwf))

        # Else, we must show a concrete page
        else:
            if hId: 
                mypage = self.getPage(hId=hId, format=format)
            else:
                mypage = self.getPage(docId=docId, format=format)

            if not mypage: 
                self.show(fname=ERROR_PAGE, format=format)
                return 5

            if action == 'edit':
                self.edit(docId, title=mypage.name, format=format)
            else:
                self.show(mypage, format=format, title=mypage.name)


    def show(self, page=None, contents=None, fname=None, format="html", title=""):
        """
        Show contents of the specified file on stdout. Depending on the type of contents,
        the appropriate header is shown before.

        If the contents are of type HTML, we add appropriate links and metadata (we could
        do the same for the other types, with a very lighweight HTML code around the
        text... but I don't like that, if people wants to just download the raw text).
        """

        if format == 'html':   
            contentsType = "text/html"

        elif format == 'pdf':  
            contentsType = "application/pdf"
            pname = fname if fname else page.name
            print 'Content-Disposition: filename="%s.pdf"' % pname.replace(' ', '_')

        else:                  
            contentsType = "text/plain"

        print "Content-type: %s" % contentsType
        if not contents:
            if fname:
                f = open(fname)
                contents = f.read()
                f.close()
            elif page:
                if hasattr(page.meta, 'version'): 
                    print "CIEMAT_howtos_version: %s" % page.meta.version
                print "CIEMAT_howtos_rstTime: %s" % page.rstTime
                print "CIEMAT_howtos_id: %s" % page.meta.id
                # Here we read from Elastic, and we get Unicode type!
                # Thus, when showing (below) we need to encode before printing
                if   format == "html":      contents = self.showWithMeta(page)
                elif format == "twiki":     contents = page.twiki
                elif format == "pdf":       contents = page.pdf
                elif format in ('md', 'markdown'):  contents = page.markdown
                else:                       contents = page.rst

        # Return the result (encode in UTF-8)
        print
        if format == 'pdf':  print contents.encode('latin-1')
        else:                
            try:
                print contents.encode('utf-8')
            except UnicodeDecodeError, inst:
                print contents.encode('latin-1')


    def showWithMeta(self, page):
        """
        Insert the top links and the side metadata (keywords, date).
        """
        params = {}
        params['title'] = page.name
        params['id'] = page.meta.id

        # Keywords
        params['kwords'] = ','.join(page.keywords)
        klink = '/howtos?kwf='
        params['kwordList'] = '\n'.join(['<li><a href="%s%s">%s</a></li>' % (klink, x, x) for x in page.keywords])

        # Human link
        if (not hasattr(page, 'hId')) or (not page.hId):  
            params['hId'] = 'UNASSIGNED' 
        else:  
            params['hId'] = page.hId

        # Metadata
        params['changeTime'] = page.rstTime.strftime('%Y-%m-%d %H:%M')
        params['htmlTime']  = page.htmlTime.strftime('%Y-%m-%d %H:%M')
        params['rstSize'] = len(page.rst)
        if page.html:  params['htmlSize'] = len(page.html)
        if hasattr(page.meta, 'version'): params['version'] = page.meta.version
        else:                         params['version'] = ''
        params['creator'] = page.creator
        params['lastUpdater'] = page.lastUpdater


        # Contents
        lines = page['html'].split('\n')

        # Up to document line
        part = []
        while lines:
            line = lines.pop(0)
            if not line.startswith('<div class="document" id='): 
                if (not line.startswith('</head>')) and (not line.startswith('<body>')):
                    part.append(line)
            else:
                params['docline'] = line
                break
        params['pre'] = '\n'.join(part)

        # From document line to the end
        part = []
        while lines:
            line = lines.pop(0)
            if not line.startswith('</body>'): 
                part.append(line)
            else:
                break
        params['most'] = '\n'.join(part)

        commonKwdOpts = ''
        for k in self.getCommonKwords():
            commonKwdOpts += '<a onclick=\\"addKword(\'%s\')\\">%s</a>' % (k, k)
        params['commonKwords'] = commonKwdOpts

        # Output results
        return self.loadFile(self.c['showTempl']) % params



    def edit(self, docId, title='', contents='', format='rst'):
        """
        Shows an editor page for the specified file name.
        """
        self.mylog('edit %s, %s, %s' % (docId, title, format))

        if  self.c['readOnly']:  
            self.mylog("ERROR: cannot 'edit' in RO mode. Ignoring.")
            return

        if format == 'md':  format = 'markdown'
        if format != 'markdown':  format = 'rst'

        print "Content-type: text/html\n"
        if not contents:  contents = getattr(self.getPage(docId=docId, format=format), format)

        params = {'contents': contents, 'title': title, 'id': docId, 'format': format}
        results = self.loadFile(self.c['editTempl']) % params
        results = results.encode('UTF-8')

        print results


    def addHowto(self, name, keywords, contents=None, format='rst', edit=False, author=None, hId=None):
        """
        Add new howto entry. By default, with basic contents.

        If 'author' is specified, it'll be stored in DB as creator and last updater of the doc.
        """
        self.mylog('add -- %s -- %s' % (name, keywords))

        if  self.c['readOnly']:  
            self.mylog("ERROR: cannot 'addHowto' in RO mode. Ignoring.")
            return

        page = self.db.getHowtoByName(name)

        # If the page exists already, abort
        if page:
            self.mylog('existing page -- %s' % (page.name))
            if edit:  self.show(fname=EXISTING_PAGE)
            else:     print("Status: 400 Bad Request -- Page exists already\n")
            return 400

        sub = '*' * (len(name)+1)
        keywords = keywords.strip().strip(',').split(',')
        if not contents:  contents = BASE_CONTENTS % ({'title': name, 'sub': sub})

        if not hId:  hId = name.replace(' ', '-').replace(',', '').replace(':', '').lower()

        docId = self.db.newHowto(name, keywords, contents, hId, author=author)

        if edit:  
            if format == 'rst':  self.edit(docId, name, contents=contents, format=format)
            else:                self.edit(docId, name, format=format)
        else:     
            print "Content-type: application/json\n"
            print json.dumps({'id': docId})

    
    def removeHowtos(self, ids):
        """
        Removes specified HowTos.
        """
        if  self.c['readOnly']:  
            self.mylog("ERROR: cannot 'removeHowtos' in RO mode. Ignoring.")
            return

        if type(ids) != list:  ids = [ids]

        names = []
        for docId in ids:
            self.mylog('delete %s' % docId)
            names.append(self.db.getHowto(docId).name + ('  (%s)' % docId))
            self.db.deleteHowto(docId)

        out = self.loadFile(self.c['delTempl'])
        print "Content-type: text/html\n"
        print out % {'hlist': '\n<br/>'.join(names)}


    def changeKwords(self, ids, keywords, replace='yes'):

        self.mylog('changeKwords %s, replace: %s' % (ids, replace))

        if  self.c['readOnly']:  
            self.mylog("ERROR: cannot 'changeKwords' in RO mode. Ignoring.")
            return

        newKwds = keywords.strip().strip(',').split(',')

        if type(ids) != list:  

            if replace == 'yes':
                kwdList = newKwds
            else:
                kwdList = self.db.getHowto(ids).keywords
                kwdList.extend(newKwds)

            self.db.update(ids, {'keywords': kwdList})
            self.output(ids)
            return 

        names = []
        for docId in ids:
            doc = self.db.getHowto(docId)
            if replace == 'yes':
                kwdList = newKwds
            else:
                kwdList = doc.keywords
                kwdList.extend(newKwds)
            self.db.update(docId, {'keywords': kwdList})
            names.append(doc.name + ('  (%s)' % docId))

            out = self.loadFile(self.c['updateKTempl'])
            print "Content-type: text/html\n"
            print out % {'hlist': '\n<br/>'.join(names)}


    def changeName(self, docId, name):

        if  self.c['readOnly']:  
            self.mylog("ERROR: cannot 'changeName' in RO mode. Ignoring.")
            return

        self.mylog('changeName %s %s' % (docId, name))
        self.db.update(docId, {'name': name})
        self.output(docId)


    def changeLink(self, docId, hId):

        if  self.c['readOnly']:  
            self.mylog("ERROR: cannot 'changeLink' in RO mode. Ignoring.")
            return

        err = False

        if not linkPattern.match(hId):
            err = True
            errmsg = "\nERROR: updating hId ('%s' for docId=%s): does not fit allowed format '%s'" % (docId, hId, linkFormat)

        if self.db.getHowtoHId(hId):
            err = True
            errmsg = "\nERROR: updating hId ('%s' for docId=%s): hId already used in DB" % (docId, hId)

        if err:
            print "Status: 400 Bad Request"
            print "Content-type: text/html\n"
            print (errmsg)
            return

        self.mylog('changeLink %s %s' % (docId, hId))
        self.db.update(docId, {'hId': hId})
        self.output(docId)


    def changeCreator(self, ids, author):

        self.mylog('changeCreator %s %s' % (ids, author))

        if  self.c['readOnly']:  
            self.mylog("ERROR: cannot 'changeCreator' in RO mode. Ignoring.")
            return

        if type(ids) != list:  
            self.db.update(ids, {'creator': author})
            self.output(ids)

        else:
            for docId in ids:
                self.db.update(docId, {'creator': author})

            out = self.loadFile(self.c['updateKTempl'])
            print "Content-type: text/html\n"
            print out % {'hlist': '\n<br/>'.join(ids)}


    def save(self, docId, contents, format="rst", version=None, author=None):
        """
        Save the passed contents on the specified page (if must have been created
        beforehand). The format must be either 'rst' (default) or 'markdown'. If the
        second is used, an automatic translation to 'rst' is performed (since this is the
        authoritative source for everything else) and DB is updated with both.

        If 'version' is specified, then ES will check if we are updating that version, 
        and not an older one (in which case, an error is returned).

        If 'author' is specified, it will be stored in the DB as last updater of the doc.
        """
        self.mylog('save docId=%s, fmt=%s, vers=%s, author=%s' % (docId, format, version, author))

        if  self.c['readOnly']:  
            self.mylog("ERROR: cannot 'save' in RO mode. Ignoring.")
            return

        tnow = datetime.now()

        if format in ('md', 'markdown'):
            params = {'markdown': contents, 'markdownTime': tnow}
            out = shell(mdown2rst + ' -', input=contents)
            params.update({'rst': out, 'rstTime': tnow})
        else:
            params = {'rst': contents, 'rstTime': tnow}

        if author:  params['lastUpdater'] = author

        # We first try to parse rst to HTML, since this is the main use case.
        # If it fails, we return an error.
        try:
            #
            # We need the input to be UTF-8 (which is what HTML editor and most PCs where
            # 'howto' CLI is run use), because if it's other enconding we won't know which
            # one it is, so how could we decode it?
            # So we assume it's already UTF-8, and thus it doesn't make sense to decode
            # and encode it again... we just use it as is.
            #
#            out = shell(rst2html + ' -', input=unicode(params['rst'], 'utf-8').encode('utf-8'))
            out = shell(rst2html + ' -', input=params['rst'])
            params['html'] = out
            params['htmlTime'] = tnow
        except Exception, ex:
            print "Status: 400 Bad Request"
            print "Content-type: text/html\n"
            print ("\nERROR: when saving %s:  **cannot parse ReST code**\n\n%s" % (docId, ex)).replace('Output:', '\n\nOutput:\n')
            return

        try:
#            self.mylog('save params = %s' % (params.keys()))
            self.db.update(docId, params, version)
            print "Content-type: text/html\n"
            print "OK"
        except Exception, ex:
            print "Status: 409 Conflict"
            print "Content-type: text/html\n"
            print "ERROR when saving %s: %s" % (docId, ex)
#        else:
#            print "Content-type: text/html\n\n"
#            print "ERROR when saving %s: can't find page" % (pageName)


    def getFrecList(self, op):
        """
        Query redis for the list of recent/common docs/kwords and return it.
        """
        print "Content-type: text/text\n"

        if op == 'commonDocs':
            temp = ["%s##H##%s" % (x.meta.id, x.name) for x in self.db.getHowtoList(self.getCommonDocs())]

        elif op == 'recentDocs':
            temp = ["%s##H##%s" % (x.meta.id, x.name) for x in self.db.getHowtoList(self.getRecentDocs())]

        elif op == 'commonKwords':
            temp = self.getCommonKwords()

        elif op == 'recentKwords':
            temp = self.getRecentKwords()

        print '\n'.join(fixcols(temp, params={'delim': '##H##'}))

### MAIN ### 

# Get URI
url = os.environ["REQUEST_URI"] 

# Get cgi values
args = cgi.FieldStorage()
docId = args.getvalue('id')
msg  = args.getvalue('msg')
format = args.getvalue('format')
if format == None:  format = 'html'
title  = args.getvalue('tf')
kword  = args.getvalue('kwf')
Nkword  = args.getvalue('Nkwf')

body   = args.getvalue('bf')
filtOp  = args.getvalue('filtOp')
action = args.getvalue('action')
howtoName = args.getvalue('howtoName')
name = args.getvalue('name')
hId = args.getvalue('hId')
# If a path like howtos/whatever is used, consider 'whatever' to be a hId
if not hId and (not 'cgi-bin' in url) and (not '?' in url) and ('/howtos/' in url):
    hId = url.split('/howtos/')[1]
keywords = args.getvalue('keywords')
replace = args.getvalue('replace')
contents = args.getvalue('contents')
direct = args.getvalue('direct')
link = args.getvalue('link')
version = args.getvalue('version')
author = args.getvalue('author')
longl = args.getvalue('longl')
qfClicked = args.getvalue('qfClicked')
#qf_ops = args.getvalue('qf_ops')
#qf = {'ops': qf_ops}

# Run the main method that returns the html result
howto = howtos()
#howto.mylogf.write('config: %s\n' % howto.c)
defaultAction = False
if link:
    howto.output(kwf=link, Nkwf=Nkword, qfClicked=qfClicked, direct=True)
elif action == 'getFrecList':
    howto.getFrecList(filtOp)
elif action == 'getMeta':
    howto.getMeta(docId, longl=longl)
elif action == 'getMetaHId':
    howto.getMeta(hId, isHId=True, longl=longl)
elif not howto.c['readOnly']: 
    if action == 'addHowto':
        howto.addHowto(howtoName, keywords, contents=contents, author=author)
    elif action == 'editNewHowto':
        if not howtoName: howto.output(None)
        if format == 'html':  format = 'rst'
        howto.addHowto(howtoName, keywords, format=format, edit=True)
    elif action == 'changeKwords':
        howto.changeKwords(docId, keywords, replace)
    elif action == 'changeName':
        howto.changeName(docId, name)
    elif action == 'changeLink':
        howto.changeLink(docId, hId)
    elif action == 'changeCreator':
        howto.changeCreator(docId, author)
    elif action == 'save':
        howto.save(docId, contents, format, version=version, author=author)
    elif action == 'remove':
        howto.removeHowtos(docId)
    else:
        defaultAction = True
else:
    defaultAction = True

if defaultAction:
#    howto.mylogf.write('Going for default action (output)\n')
    howto.output(docId, title, kword, body, filtOp, format, action, direct=direct, longl=longl, 
                 Nkwf=Nkword, qfClicked=qfClicked, hId=hId)

