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
BASEDIR = '/var/www/html/howtos'
CGIDIR = '/var/www/cgi-bin/howtos'
howtoDir = os.path.join(BASEDIR, 'data')
newDir = os.path.join(BASEDIR, 'new')
privateHowtos = os.path.join(howtoDir, '.private')
showTempl = os.path.join(BASEDIR, 'show.templ')
editTempl = os.path.join(BASEDIR, 'edit.templ')
iniTempl  = os.path.join(BASEDIR, 'ini.templ')
delTempl = os.path.join(BASEDIR, 'deleted.templ')
updateKTempl = os.path.join(BASEDIR, 'updateK.templ')

txt2html = CGIDIR + '/simplish.py'
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
                    self.db.update(mypage.meta.id, {'markdown': out, 'markdownTime': datetime.now()})
                    mypage = self.db.getHowto(id)

            if format == 'html':

                # Check if HTML field is there and is up-to-date. If not, produce it and store it
                if (not mypage.html) or (not mypage.htmlTime) or (mypage.htmlTime < mypage.rstTime):
                    out = shell(rst2html + ' -', input=mypage.rst.encode('utf-8'))
                    self.db.update(mypage.meta.id, {'html': out, 'htmlTime': datetime.now()})
                    mypage = self.db.getHowto(id)

            elif format == 'twiki':

                # Check if Twiki field is there and is up-to-date. If not, produce it and store it
                if ('twiki' not in mypage) or ('twikiTime' not in mypage) or (mypage.twikiTime < mypage.rstTime):
#                    self.mylog("Going into Twiki production")
                    out = shell(rst2twiki + ' -', input=mypage.rst.encode('utf-8'))
                    self.db.update(mypage.meta.id, {'twiki': out, 'twikiTime': datetime.now()})
                    mypage = self.db.getHowto(id)

            elif format == 'pdf':

                # Check if PDF field is there and is up-to-date. If not, produce it and store it
                if ('pdf' not in mypage) or ('pdfTime' not in mypage) or (mypage.pdfTime < mypage.rstTime):
                    out = shell(rst2pdf + ' -', input=mypage.rst.encode('utf-8'))
                    self.mylog("PDF produced: %s" % mypage.name)
                    # Apparently PDF is produced in latin-1, so it's easier to store it in DB in latin-1
                    # (otherwise failures happen...). When storing in the DB, we explicitely 
                    # convert to unicode to indicate that latin-1 should be used to decode
                    self.db.update(mypage.meta.id, {'pdf': unicode(out, encoding='latin-1'), 'pdfTime': datetime.now()})
                    self.mylog("....After DB update")
                    mypage = self.db.getHowto(id)


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


    def produceIndex(self, rows=None, titleFilter=[], kwordFilter=[], bodyFilter=[], filtOp='$or', NkwordFilter=[]):
        """
        Produce an index page to look for documents.
        """
        baseFilt  = "&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;"
        baseFilt += """<input type="radio" name="filtOp" value="$or"  %s>OR</input>"""  % ('checked' if filtOp!='$and' else '')
        baseFilt += """&nbsp;<input type="radio" name="filtOp" value="$and" %s>AND</input>""" % ('checked' if filtOp=='$and' else '')

#        baseKword = """&nbsp;Title/Kword filter: <input type="text" class="filter" name="kwordFilter" value="%s" />"""
#        baseBody  = """&nbsp;&nbsp;&nbsp; Contents filter: <input type="text" class="filter" name="bodyFilter" value="%s" />""" 
        baseKword = """<input type="text" size="25" class="filter" name="kwordFilter" value="%s" autofocus />"""
        baseBody  = """<input type="text" class="filter" name="bodyFilter" value="%s" />""" 
        
        baseNKword = """<input type="text" class="filter" name="NkwordFilter" value="%s" />"""
        
        text = self.loadFile(iniTempl)

        def createText(mylist, buttonText, baseText):
            if not mylist:  mylist = [""]
            mytext = """<input type="button" value="+" onclick="%s" />""" % buttonText
            mytext  += "<br/>\n".join([baseText % elem  for elem in mylist])
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
            'NkwordFilter': createText(NkwordFilter, 'addNKwordFilter()', baseNKword),
            'bodyFilter':  createText(bodyFilter, 'addBodyFilter()', baseBody),
            'common': commonPart, 'recent': recentPart, 'list': mainPart,
            'baseFilt': baseFilt, 'commonKwords': commonKwdOpts,
        }

        return text % map


    def output(self, id=None, titleFilter=[], kwordFilter=[], bodyFilter=[], filtOp=None,
               format='html', action='show', direct=False, longl=False, NkwordFilter=[]):
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

        if not NkwordFilter:  NkwordFilter = []
        elif type(NkwordFilter) != list:  NkwordFilter = [NkwordFilter]

        if not bodyFilter:  bodyFilter = []
        elif type(bodyFilter)  != list:   bodyFilter = [bodyFilter]

        if not filtOp:  filtOp = '$or'

        # If action was list, return json
        if action == 'list':

            # Get matching docs
            rows = self.db.filter(names=titleFilter, kwords=kwordFilter, contents=bodyFilter, op=filtOp, Nkwords=NkwordFilter)

            # Return appropiate json 
            self.list(rows, longl=longl)

        # If no id is given, filter the DB
        elif (not id) or (id == 'index.html'):

            # Get matching docs
            rows = self.db.filter(names=titleFilter, kwords=kwordFilter, contents=bodyFilter, op=filtOp, Nkwords=NkwordFilter)

            # If only one match (and 'direct' flag), show it directly
            if direct and (len(rows) == 1):
                self.show(rows[0], format=format, title=rows[0].name)

            # Else, produce the page showing the complete list
            else:
                self.show(contents=self.produceIndex(rows, titleFilter, kwordFilter, bodyFilter, filtOp, 
                                                     NkwordFilter=NkwordFilter))

        # Else, we must show a concrete page
        else:

            mypage = self.getPage(id, format)

            if not mypage: 
                self.show(fname=ERROR_PAGE, format=format)
                return 5

            if action == 'edit':
                self.edit(id, title=mypage.name, format=format)
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
                if hasattr(page, '_version'): 
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
        if hasattr(page, '_version'): params['version'] = page._version
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
        return self.loadFile(showTempl) % params



    def edit(self, id, title='', contents='', format='rst'):
        """
        Shows an editor page for the specified file name.
        """
        self.mylog('edit %s, %s, %s' % (id, title, format))

        if format == 'md':  format = 'markdown'
        if format != 'markdown':  format = 'rst'

        print "Content-type: text/html\n"
        if not contents:  contents = getattr(self.getPage(id, format=format), format)

        params = {'contents': contents, 'title': title, 'id': id, 'format': format}
        results = self.loadFile(editTempl) % params
        results = results.encode('UTF-8')

        print results


    def addHowto(self, name, keywords, contents=None, format='rst', edit=False, author=None):
        """
        Add new howto entry. By default, with basic contents.

        If 'author' is specified, it'll be stored in DB as creator and last updater of the doc.
        """
        self.mylog('add -- %s -- %s' % (name, keywords))
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

        id = self.db.newHowto(name, keywords, contents, author=author)

        if edit:  
            if format == 'rst':  self.edit(id, name, contents=contents, format=format)
            else:                self.edit(id, name, format=format)
        else:     
            print "Content-type: application/json\n"
            print json.dumps({'id': id})

    
    def removeHowtos(self, ids):
        """
        Removes specified HowTos.
        """
        if type(ids) != list:  ids = [ids]

        names = []
        for id in ids:
            self.mylog('delete %s' % id)
            names.append(self.db.getHowto(id).name + ('  (%s)' % id))
            self.db.deleteHowto(id)

        out = self.loadFile(delTempl)
        print "Content-type: text/html\n"
        print out % {'hlist': '\n<br/>'.join(names)}


    def changeKwords(self, ids, keywords, replace='yes'):
        self.mylog('changeKwords %s, replace: %s' % (ids, replace))

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
        for id in ids:
            doc = self.db.getHowto(id)
            if replace == 'yes':
                kwdList = newKwds
            else:
                kwdList = doc.keywords
                kwdList.extend(newKwds)
            self.db.update(id, {'keywords': kwdList})
            names.append(doc.name + ('  (%s)' % id))

            out = self.loadFile(updateKTempl)
            print "Content-type: text/html\n"
            print out % {'hlist': '\n<br/>'.join(names)}


    def changeName(self, id, name):
        self.mylog('changeName %s %s' % (id, name))
        self.db.update(id, {'name': name})
        self.output(id)


    def changeCreator(self, ids, author):

        self.mylog('changeCreator %s %s' % (ids, author))

        if type(ids) != list:  
            self.db.update(ids, {'creator': author})
            self.output(ids)

        else:
            for id in ids:
                self.db.update(id, {'creator': author})

            out = self.loadFile(updateKTempl)
            print "Content-type: text/html\n"
            print out % {'hlist': '\n<br/>'.join(ids)}


    def save(self, id, contents, format="rst", version=None, author=None):
        """
        Save the passed contents on the specified page (if must have been created
        beforehand). The format must be either 'rst' (default) or 'markdown'. If the
        second is used, an automatic translation to 'rst' is performed (since this is the
        authoritative source for everything else) and DB is updated with both.

        If 'version' is specified, then ES will check if we are updating that version, 
        and not an older one (in which case, an error is returned).

        If 'author' is specified, it will be stored in the DB as last updater of the doc.
        """
        self.mylog('save id=%s, fmt=%s, vers=%s, author=%s' % (id, format, version, author))

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
            print ("\nERROR: when saving %s:  **cannot parse ReST code**\n\n%s" % (id, ex)).replace('Output:', '\n\nOutput:\n')
            return

        try:
#            self.mylog('save params = %s' % (params.keys()))
            self.db.update(id, params, version)
            print "Content-type: text/html\n"
            print "OK"
        except Exception, ex:
            print "Status: 409 Conflict"
            print "Content-type: text/html\n"
            print "ERROR when saving %s: %s" % (id, ex)
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

# Get cgi values
args = cgi.FieldStorage()
id = args.getvalue('id')
msg  = args.getvalue('msg')
format = args.getvalue('format')
if format == None:  format = 'html'
title  = args.getvalue('titleFilter')
kword  = args.getvalue('kwordFilter')
Nkword  = args.getvalue('NkwordFilter')
body   = args.getvalue('bodyFilter')
filtOp  = args.getvalue('filtOp')
action = args.getvalue('action')
howtoName = args.getvalue('howtoName')
#addHowto  = args.getvalue('addHowto')
#changeKwords  = args.getvalue('changeKwords')
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
elif action == 'addHowto':
    howto.addHowto(howtoName, keywords, contents=contents, author=author)
elif action == 'editNewHowto':
    if not howtoName: howto.output(None)
    if format == 'html':  format = 'rst'
    howto.addHowto(howtoName, keywords, format=format, edit=True)
elif action == 'changeKwords':
    howto.changeKwords(id, keywords, replace)
elif action == 'changeName':
    howto.changeName(id, name)
elif action == 'changeCreator':
    howto.changeCreator(id, author)
elif action == 'save':
    howto.save(id, contents, format, version=version, author=author)
elif action == 'remove':
    howto.removeHowtos(id)
elif action == 'getFrecList':
    howto.getFrecList(filtOp)

else:
    howto.output(id, title, kword, body, filtOp, format, action, direct=direct, longl=longl, NkwordFilter=Nkword)
