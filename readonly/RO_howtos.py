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
BASEDIR = '/var/www/html/howtos/readonly'
CGIDIR = '/var/www/cgi-bin/howtos/'
howtoDir = os.path.join('/var/www/html/howtos/data')
newDir = os.path.join(BASEDIR, 'new')
privateHowtos = os.path.join(howtoDir, '.private')
showTempl = os.path.join(BASEDIR, 'show.templ')
iniTempl  = os.path.join(BASEDIR, 'ini.templ')

txt2html = CGIDIR + '/simplish.py'
rst2html = CGIDIR + '/txt2html/command2.sh'
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

numCommon = 8
numRecent = 8
#maxRecent = numRecent**2
numKwords = 12

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
        
        # Connect to mongoDB
        self.db = ElasticIface()

        # Connect to redis also
        self.cache = redis.StrictRedis(unix_socket_path='/tmp/redis.sock')


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


    def getPage(self, id, format='html'):
        """
        Get a Howto and return it as text/html/twiki.
        """
        try:
            # Here we get the RST contents from ES, in Unicode type
            # Thus, we'd better encode them before passing to shell for HTML/twiki.. production

            mypage = self.db.getHowto(id)
            if not mypage: return None
#            self.mylog("MYPAGE: %s" % mypage)

            # Add the page to the caches 
            self.cache.lrem('recentDocs', 1, id)
            self.cache.lpush('recentDocs', id)
            self.cache.ltrim('recentDocs', 0, numRecent)
            self.cache.zincrby('commonDocs', id, amount=1)
           
            if format in ('md', 'markdown'):

                # Check if Markdown field is there and is up-to-date. If not, produce it and store it
                if ('markdown' not in mypage) or ('markdownTime' not in mypage) or (mypage.markdownTime < mypage.rstTime):
                    out = shell(rst2mdown + ' -', input=mypage.rst.encode('utf-8'))
                    mypage.markdown = out

            if format == 'html':

                # Check if HTML field is there and is up-to-date. If not, produce it and store it
                if (not mypage.html) or (not mypage.htmlTime) or (mypage.htmlTime < mypage.rstTime):
                    out = shell(rst2html + ' -', input=mypage.rst.encode('utf-8'))
                    mypage.html = out
                    mypage.htmlTime = datetime.now()

            elif format == 'twiki':

                # Check if Twiki field is there and is up-to-date. If not, produce it and store it
                if ('twiki' not in mypage) or ('twikiTime' not in mypage) or (mypage.twikiTime < mypage.rstTime):
                    out = shell(rst2twiki + ' -', input=mypage.rst.encode('utf-8'))
                    mypage.twiki = out

            elif format == 'pdf':

                # Check if PDF field is there and is up-to-date. If not, produce it and store it
                if ('pdf' not in mypage) or ('pdfTime' not in mypage) or (mypage.pdfTime < mypage.rstTime):
                    out = shell(rst2pdf + ' -', input=mypage.rst.encode('utf-8'))
                    self.mylog("PDF produced: %s" % mypage.name)
                    # Apparently PDF is produced in latin-1, so it's easier to store it in DB in latin-1
                    # (otherwise failures happen...). When storing in the DB, we explicitely 
                    # convert to unicode to indicate that latin-1 should be used to decode
                    mypage.pdf = unicode(out, encoding='latin-1')


            # Add the associated keywords to the caches
            for kword in mypage.keywords:
                self.cache.lrem('recentKwords', 1, kword)
                self.cache.lpush('recentKwords', kword)
                self.cache.ltrim('recentKwords', 0, numRecent)
                self.cache.zincrby('commonKwords', kword, amount=1)

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
            id = row.meta.id
            if (not id in self.privatePages):
                    mylink = 'href="howtos.py?id=%s' % id
                    if (cont % 4) == 0: text += '\n<tr>'
                    text += '\n<td>'
                    text += '<a class="howtoLink" %s">%s</a>' % (mylink, title)
                    text += '&nbsp;&nbsp;&nbsp;<br/>'
                    linkList = ['<a class="smLink" href="howtos.py?kwordFilter=%s">%s</a>' % (x,x) for x in row.keywords]
                    text += ' &nbsp;'.join(linkList)
                    text += '&nbsp;&nbsp;<br/>&nbsp;</td>'
                    if (cont % 4) == 3: text += '\n</tr>' 
                    cont += 1
        text += '\n' # <tr><td colspan="4"><hr></td></tr>'

        return text


    def list(self, rows, longl=False):
        """
        Produce a json list of matching howtos (returns id, name and kwords only).
        """
        result = []
        for row in rows:
            elem = {'name': row.name, 'id': row.meta.id, 'kwords': ','.join(row.keywords)}
            if longl: 
                mypage = self.db.getHowto(row.meta.id)
                elem['version'] = mypage._version
                elem['creator'] = mypage.creator
                elem['lastUpdater'] = mypage.lastUpdater
                elem['rstTime'] = mypage.rstTime.strftime('%Y-%m-%d %H:%M')
            result.append(elem)

            # Note: it seems that listed doc do not include version info, so we cannot use the following 
#            result.append({'name': row.name, 'id': row.meta.id, 'kwords': ','.join(row.keywords), 'version': row._version})

        print "Content-type: application/json\n" 
        print json.dumps(result)


    def produceIndex(self, rows=None, titleFilter=[], kwordFilter=[], bodyFilter=[], filtOp='$or'):
        """
        Produce an index page to look for documents.
        """
        baseFilt  = "&emsp; &emsp; &emsp; &emsp; &emsp; &emsp; &emsp; &emsp; &emsp; &emsp; &emsp;"
        baseFilt += """<input type="radio" name="filtOp" value="$or"  %s>OR</input>"""  % ('checked' if filtOp!='$and' else '')
        baseFilt += """&nbsp;<input type="radio" name="filtOp" value="$and" %s>AND</input>""" % ('checked' if filtOp=='$and' else '')

        baseKword = """&nbsp;Title/Kword filter: <input type="text" class="filter" name="kwordFilter" value="%s" />"""
        baseBody  = """&nbsp;&nbsp;&nbsp; Contents filter: <input type="text" class="filter" name="bodyFilter" value="%s" />""" 
        
        text = self.loadFile(iniTempl)

        def createText(mylist, buttonText, baseText):
            if not mylist:  mylist = [""]
            mytext = """<input type="button" value="+" onclick="%s" />""" % buttonText
            mytext  += "<br/>\n&nbsp; &nbsp; ".join([baseText % elem  for elem in mylist])
            return mytext


        sectionText = '<tr><td colspan="4"><br/><span class="mylabel">%s</span><hr></td></tr>'
        mainList = self.howtoList(rows) if rows!=None else self.howtoList(self.db.filter(titleFilter, kwordFilter, bodyFilter))

        commonKwords = self.getCommonKwords()
        if not (titleFilter or kwordFilter or bodyFilter):

            mainPart = sectionText % ('All docs') + mainList

            recentPart = sectionText % ('Recently visited')
            recentList = self.db.getHowtoList(self.getRecentDocs())
            rKwds = ['<a class="smLink2" href="howtos.py?kwordFilter=%s">%s</a>' % (x,x) for x in self.getRecentKwords()]
            if rKwds:
                recentPart += '<tr><td colspan="4">' + ' &nbsp; '.join(rKwds) + '<br/><hr></td></tr>'
            if recentList:
                recentPart += self.howtoList(recentList)

            commonList = self.db.getHowtoList(self.getCommonDocs())
            commonPart = sectionText % ('Most visited') 
            cKwds = ['<a class="smLink2" href="howtos.py?kwordFilter=%s">%s</a>' % (x,x) for x in commonKwords]
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
            'kwordFilter': createText(kwordFilter, 'addKwordFilter()', baseKword),
            'bodyFilter':  createText(bodyFilter, 'addBodyFilter()', baseBody),
            'common': commonPart, 'recent': recentPart, 'list': mainPart,
            'baseFilt': baseFilt, 'commonKwords': commonKwdOpts,
        }

        return text % map


    def output(self, id=None, titleFilter=[], kwordFilter=[], bodyFilter=[], filtOp=None,
               format='html', action='show', direct=False, longl=False):
        """
        Basic method to display the index page (with appropriate filter) or
        a howto page in the specified format, or the edition page, or even a 
        simple info message.
        """
        self.mylog("In output: %s, %s" % (action, format))

        # Sanitize filters (at least one filter of each, but by default containing nothing)
        if not titleFilter:  titleFilter = []
        elif type(titleFilter) != list:  titleFilter = [titleFilter]

        if not kwordFilter:  kwordFilter = []
        elif type(kwordFilter) != list:  kwordFilter = [kwordFilter]

        if not bodyFilter:  bodyFilter = []
        elif type(bodyFilter)  != list:   bodyFilter = [bodyFilter]

        if not filtOp:  filtOp = '$or'

        # If action was list, return json
        if action == 'list':

            # Get matching docs
            rows = self.db.filter(names=titleFilter, kwords=kwordFilter, contents=bodyFilter, op=filtOp)

            # Return appropiate json 
            self.list(rows, longl=longl)

        # If no id is given, filter the DB
        elif (not id) or (id == 'index.html'):

            # Get matching docs
            rows = self.db.filter(names=titleFilter, kwords=kwordFilter, contents=bodyFilter, op=filtOp)

            # If only one match (and 'direct' flag), show it directly
            if direct and (len(rows) == 1):
                self.show(rows[0], format=format, title=rows[0].name)

            # Else, produce the page showing the complete list
            else:
                self.show(contents=self.produceIndex(rows, titleFilter, kwordFilter, bodyFilter, filtOp))

        # Else, we must show a concrete page
        else:

            mypage = self.getPage(id, format)

            if not mypage: 
                self.show(fname=ERROR_PAGE, format=format)
                return 5

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
                print "CIEMAT_howtos_version: %s" % page._version
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
            except UnicodeDecodeError as inst:
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
        klink = 'howtos.py?kwordFilter='
        params['kwordList'] = '\n'.join(['<li><a href="%s%s">%s</a></li>' % (klink, x, x) for x in page.keywords])

        # Metadata
        params['changeTime'] = page.rstTime.strftime('%Y-%m-%d %H:%M')
        params['htmlTime']  = page.htmlTime.strftime('%Y-%m-%d %H:%M')
        params['rstSize'] = len(page.rst)
        if page.html:  params['htmlSize'] = len(page.html)
        params['version'] = page._version
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
        return self.loadFile(showTempl) % params


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

# Get cgi values
args = cgi.FieldStorage()
id = args.getvalue('id')
msg  = args.getvalue('msg')
format = args.getvalue('format')
if format == None:  format = 'html'
title  = args.getvalue('titleFilter')
kword  = args.getvalue('kwordFilter')
body   = args.getvalue('bodyFilter')
filtOp  = args.getvalue('filtOp')
action = args.getvalue('action')
howtoName = args.getvalue('howtoName')
name = args.getvalue('name')
keywords = args.getvalue('keywords')
replace = args.getvalue('replace')
contents = args.getvalue('contents')
direct = args.getvalue('direct')
link = args.getvalue('link')
version = args.getvalue('version')
author = args.getvalue('author')
longl = args.getvalue('longl')

# Run the main method that returns the html result
howto = howtos()
if link:
    howto.output(titleFilter=link, direct=True)
elif action == 'getFrecList':
    howto.getFrecList(filtOp)

else:
    howto.output(id, title, kword, body, filtOp, format, action, direct=direct, longl=longl)
