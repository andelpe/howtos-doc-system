#!/usr/bin/env python

#from __future__ import division, print_function


### IMPORTS ###
import os, logging, time
import re
import subprocess as sub
import cgi
from elasticIface import ElasticIface
import bson
from utils import shell, commandError
from datetime import datetime


### CONSTANTS ####
BASEDIR = '/var/www/html/howtos'
CGIDIR = '/var/www/cgi-bin/howtos'
howtoDir = os.path.join(BASEDIR, 'data')
newDir = os.path.join(BASEDIR, 'new')
privateHowtos = os.path.join(howtoDir, '.private')
showTempl = os.path.join(BASEDIR, 'show.templ')
editTempl = os.path.join(BASEDIR, 'edit3.templ')
iniTempl  = os.path.join(BASEDIR, 'ini.templ')

txt2html = CGIDIR + '/simplish.py'
rst2html = CGIDIR + '/txt2html/command2.sh'
rst2twiki = CGIDIR + '/rst2twiki'
rst2pdf = CGIDIR + '/txt2pdf/command2.sh'

ERROR_PAGE = os.path.join(BASEDIR, 'error.html')
EXISTING_PAGE = os.path.join(BASEDIR, 'existing.html')

BASE_CONTENTS = """%(title)s
%(sub)s

.. contents:: Table of Contents
.. sectnum::

Intro
=====
"""


### FUNCTIONS ####
#def shell(command):
#    """
#    Runs the specified command (string) in a shell and returns the output 
#    of the command (stdout and stderr together with 2>&1) and its exit code
#    in a list like:
#       [output, exitcode]
#    """
#    p = sub.Popen(command + ' 2>&1', shell = True, stdout=sub.PIPE)
#    p.wait()
#    res = p.communicate()
#    res = [res[0], p.returncode]
#    return res


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

# TODO: pre-load things is not very effective is the script is called anew each time
#       We are actually reading files we are often not using...

        # Pre-load show (html) template
        f = open(showTempl)
        self.showTempl = f.read()
        f.close()

        # Pre-load edit template
        f = open(editTempl)
        self.editTempl = f.read()
        f.close()

        # Prepare logfile
        self.logf = open(logfile, 'a')
        
        # Connect to mongoDB
        self.db = ElasticIface()


    def log(self, msg):
        """
        Log specified message to defined logfile.
        """
        self.logf.write('%s %s \n' % (time.strftime('%Y-%m-%d %H:%M:%S'), msg))


#    def getPage(self, id, format='html', newAlso=False):
    def getPage(self, id, format='html'):
        """
        Get a Howto and return it as text/html/twiki.
        """
        try:
            # TODO: private pages will have a private tag... implement that

            mypage = self.db.getHowto(id)
            if not mypage: return None
#            self.log("MYPAGE: %s" % mypage)

            if format == 'html':

                # Check if HTML field is there and is up-to-date. If not, produce it and store it
                if (not mypage.html) or (not mypage.htmlTime) or (mypage.htmlTime < mypage.rstTime):
                    out = shell(rst2html + ' -', input=mypage.rst.encode('utf-8'))
                    self.db.update(mypage.meta.id, {'html': out, 'htmlTime': datetime.now()})
                    mypage = self.db.getHowto(id)


            elif format == 'twiki':

                # Check if Twiki field is there and is up-to-date. If not, produce it and store it
                if ('twiki' not in mypage) or ('twikiTime' not in mypage) or (mypage.twikiTime < mypage.rstTime):
#                    self.log("Going into Twiki production")
                    out = shell(rst2twiki + ' -', input=mypage.rst.encode('utf-8'))
                    self.db.update(mypage.meta.id, {'twiki': out, 'twikiTime': datetime.now()})
                    mypage = self.db.getHowto(id)

            elif format == 'pdf':

                # Check if PDF field is there and is up-to-date. If not, produce it and store it
                if ('pdf' not in mypage) or ('pdfTime' not in mypage) or (mypage.pdfTime < mypage.rstTime):
#                    self.log("Going into PDF production")
                    out = shell(rst2pdf + ' -', input=mypage.rst.encode('latin-1'))
                    out = out.decode("latin-1")
                    self.db.update(mypage.meta.id, {'pdf': out, 'pdfTime': datetime.now()})
                    mypage = self.db.getHowto(id)

            # All OK
            return mypage

        except Exception, inst:
            # TODO: Improve this
            self.log("EXCEPTION: %s" % inst)
            return None


#    def checkBodyFilter(self, filter, page):
#        """
#        """
#        if not filter: return True
#
#        fname = os.path.join(howtoDir, page)
#        f = open(fname)
#        text = f.read()
#        f.close()
#
#        for elem in filter:
#            if elem and (not re.search(elem, text)): return False
#
#        return True


    def howtoList(self, titleFilter, kwordFilter, bodyFilter):
        """
        Return the list of files in the Howto dir
        """
        text = '<table>'
        cont = 0
        rows = self.db.filter(names=titleFilter, kwords=kwordFilter, contents=bodyFilter)
        for row in rows:
            title = row.name
            id = row.meta.id
            if (not id in self.privatePages):
                    mylink = 'href="howtos3.py?id=%s' % id
                    if (cont % 4) == 0: text += '\n<tr>'
                    text += '\n<td>'
#                    text += '<a %s&format=html">%s</a>' % (mylink, page.split('.rst')[0])
#                    text += '<a %s&format=html">%s</a>' % (mylink, title)
                    text += '<a %s">%s</a>' % (mylink, title)
                    text += '&nbsp;&nbsp;&nbsp;<br/>'
                    text += '<a class="smLink" %s&format=rst">rst</a>, &nbsp; ' % mylink
                    text += '<a class="smLink" %s&format=twiki">twiki</a>, &nbsp;' % mylink
                    text += '<a class="smLink" %s&format=pdf">pdf</a>, &nbsp;' % mylink
                    text += '<a class="smLink" %s&action=edit">edit</a>' % mylink
                    text += '&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;<br/>&nbsp;</td>'
                    if (cont % 4) == 3: text += '\n</tr>' 
                    cont += 1
        text += '\n</table>'

        return text


    def produceIndex(self, titleFilter=[], kwordFilter=[], bodyFilter=[]):
        """
        Produce an index page to look for documents.
        """

        baseTitle = """&nbsp; &nbsp; 
Title filter: <input type="text" class="filter" name="titleFilter" value="%s" autofocus="autofocus"/>"""
        baseKword = """&nbsp; Keyword filter: <input type="text" class="filter" name="kwordFilter" value="%s" />"""
        baseBody = """&nbsp;Contents filter: <input type="text" class="filter" name="bodyFilter" value="%s" />""" 
        
#        f = open(iniTempl)
#        text = f.read()
#        f.close()
        with open(iniTempl) as f:
            text = f.read()

        def createText(mylist, buttonText, baseText):
            if not mylist:  mylist = [""]
            mytext = """<input type="button" value="+" onclick="%s" />""" % buttonText
            mytext  += "<br/>\n&nbsp; &nbsp; ".join([baseText % elem  for elem in mylist])
            return mytext

#        titleText = createText(titleFilter, 'addTitleFilter()', baseTitle)
#        kwordText = createText(kwordFilter, 'addKwordFilter()', baseKword)
#        bodyText  = createText(bodyFilter, 'addBodyFilter()', baseBody)

#        titleText = """<input type="button" value="+" onclick="addTitleFilter()" />"""
#        titleText += "<br/>\n&nbsp; &nbsp; ".join([baseTitle % elem  for elem in titleFilter]) 
#        kwordText = """<input type="button" value="+" onclick="addKwordFilter()" />"""
#        kwordText += "<br/>\n&nbsp; &nbsp; ".join([baseKword % elem  for elem in kwordFilter]) 
#        bodyText = """<input type="button" value="+" onclick="addBodyFilter()" />"""
#        bodyText += "<br/>\n&nbsp; &nbsp; ".join([baseBody % elem  for elem in bodyFilter]) 

        map = {
            'titleFilter': createText(titleFilter, 'addTitleFilter()', baseTitle),
            'kwordFilter': createText(kwordFilter, 'addKwordFilter()', baseKword),
            'bodyFilter':  createText(bodyFilter, 'addBodyFilter()', baseBody),
            'list': self.howtoList(titleFilter, kwordFilter, bodyFilter),
        }

        return text % map


    def output(self, id=None, titleFilter=[], kwordFilter=[], bodyFilter=[], 
               format='html', action='show'):
        """
        Basic method to display the index page (with appropriate filter) or
        a howto page in the specified format, or even the edition page. 
        """

        # Sanitize filters (at least one filter of each, but by default containing nothing)
        if not titleFilter:  titleFilter = []
        elif type(titleFilter) != list:  titleFilter = [titleFilter]

        if not kwordFilter:  kwordFilter = []
        elif type(kwordFilter) != list:  kwordFilter = [kwordFilter]

        if not bodyFilter:  bodyFilter = []
        elif type(bodyFilter)  != list:   bodyFilter = [bodyFilter]

        # Show index
        if (not id) or (id == 'index.html'):
            self.show(contents=self.produceIndex(titleFilter, kwordFilter, bodyFilter))

        # Show page
        else:

            
            if action == 'edit':  format = 'rst'
            mypage = self.getPage(id, format)

            if not mypage: 
#                self.show(fname=ERROR_PAGE, contentsType="text/html")
                self.show(fname=ERROR_PAGE, format=format)
                return 5

            if action == 'edit':
                self.edit(id, title=mypage.name, contents=mypage.rst)
            else:
#                mytype="text/plain"
#                if format == 'html':  mytype="text/html"
                self.show(mypage, format=format, title=mypage.name)


#    def show(self, page=None, contents=None, fname=None, contentsType="text/html", title=""):
    def show(self, page=None, contents=None, fname=None, format="html", title=""):
        """
        Show contents of the specified file on stdout. Depending on the type of contents,
        the appropriate header is shown before.

        If the contents are of type HTML, we add appropriate links and metadata (we could
        do the same for the other types, with a very lighweight HTML code around the
        text... but I don't like that, if people wants to just download the raw text).
        """

        if format == 'html':   contentsType = "text/html"
        elif format == 'pdf':  contentsType = "application/pdf"
        else:                  contentsType = "text/plain"

        print "Content-type: %s\n" % contentsType
        if not contents:
            if fname:
                f = open(fname)
                contents = f.read()
                f.close()
            elif page:
                if   format == "html":   contents = self.showWithMeta(page)
                elif format == "twiki":  contents = page.twiki
                elif format == "pdf":    contents = page.pdf
                else:                    contents = page.rst

        # Return the result
        if format == 'pdf':  print contents.encode('latin-1')
        else:                print contents.encode('utf-8')


    def showWithMeta(self, page):
        """
        Insert the top links and the side metadata (keywords, date).
        """
        params = {}
        params['title'] = page.name
        params['id'] = page.meta.id

        # Keywords
        params['kwords'] = page.keywords
        params['kwords'] = '\n'.join(['<li>%s</li>' % x for x in params['kwords']])

        # Metadata
        params['changeTime'] = page.rstTime.strftime('%Y-%m-%d %H:%M')
        params['htmlTime']  = page.htmlTime.strftime('%Y-%m-%d %H:%M')
        params['rstSize'] = len(page.rst)
        if page.html:  params['htmlSize'] = len(page.html)

        # Contents
        lines = page['html'].split('\n')

        # Up to document line
        part = []
        while lines:
            line = lines.pop(0)
            if not line.startswith('<div class="document" id='): 
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

        # Output results
        return self.showTempl % params


    def edit(self, id, title='', contents=''):
        """
        Shows an editor page for the specified file name.
        """
        self.log('edit %s, %s' % (id, title))
        print "Content-type: text/html\n\n"
        if not contents:  contents = getPage(id, format='rst').rst

        print self.editTempl % {'contents': contents, 'title': title, 'id': id}


    # TODO: make this work
    def addHowto(self, name, keywords, contents=None, edit=False):
        """
        Add new howto entry. By default, with basic contents.
        """
        page = self.db.getHowtoByName(name)

        # If the page exists already, abort
        if page:
            self.show(EXISTING_PAGE)
            return

        sub = '*' * len(name)
        basecontents = BASE_CONTENTS % ({'title': name, 'sub': sub})

        id = self.db.newHowto(name, tokens, rst)

        if edit:  self.edit(id, name, contents=basecontents)


    def save(self, id, contents):
        """
        Save the passed RST contents on the specified page (if must have been created
        beforehand).
        """
        self.log('save %s' % id)

        try:
            self.db.update(id, {'rst': contents, 'rstTime': datetime.now()})
#           mypage = self.db.getHowto(id)
            print "Content-type: text/html\n\n"
            print "OK"
        except Exception, ex:
            print "Content-type: text/html\n\n"
            print "ERROR when saving %s: %s" % (id, ex)
#        else:
#            print "Content-type: text/html\n\n"
#            print "ERROR when saving %s: can't find page" % (pageName)


    # TODO: uses of this should basically be replaced by 'save'
    def remoteUpdate(self, pageName, msg="Update"):
        """
        Commit update page into mercurial repo.
        """
        self.log('remoteUpdate %s' % pageName)

        os.chdir(howtoDir)
        try:
#            out = shell("hg ci -A -u howtos.py -m 'Remote - %s' %s" % (msg, pageName))
            print "Content-type: text/html\n\n"
            print "OK"
        except commandError, ex: 
            print "Content-type: text/html\n\n"
            print "ERROR when remote-updating %s: %s" % (pageName, ex)


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
action = args.getvalue('action')
addHowto  = args.getvalue('addHowto')
howtoName = args.getvalue('howtoName')
keywords = args.getvalue('keywords')

# Run the main method that returns the html result
howto = howtos()
if addHowto:
    if not howtoName: howto.output(None)
    howto.addHowto(howtoName, keywords, edit=True)
elif action == 'save':
    contents = args.getvalue('contents')
    howto.save(id, contents)
elif action == 'add':
    contents = args.getvalue('contents')
    howto.add(id, contents)
elif action == 'remoteUpdate':
    howto.remoteUpdate(page, msg)
else:
    howto.output(id, title, kword, body, format, action)
