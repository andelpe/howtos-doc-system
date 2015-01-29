#!/usr/bin/env python

#from __future__ import division, print_function


### IMPORTS ###
import os, logging, time
import re
import subprocess as sub
import cgi
from mongoIface import mongoIface


### CONSTANTS ####
BASEDIR = '/var/www/html/howtos'
CGIDIR = '/var/www/cgi-bin/howtos'
howtoDir = os.path.join(BASEDIR, 'data')
newDir = os.path.join(BASEDIR, 'new')
privateHowtos = os.path.join(howtoDir, '.private')
showTempl = os.path.join(BASEDIR, 'show.templ')
editTempl = os.path.join(BASEDIR, 'edit.templ')
iniTempl  = os.path.join(BASEDIR, 'ini.templ')

txt2html = CGIDIR + '/simplish.py'
rst2html = CGIDIR + '/txt2html/command2.sh'
rst2twiki = CGIDIR + '/rst2twiki'

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
def shell(command):
    """
    Runs the specified command (string) in a shell and returns the output 
    of the command (stdout and stderr together with 2>&1) and its exit code
    in a list like:
       [output, exitcode]
    """
    p = sub.Popen(command + ' 2>&1', shell = True, stdout=sub.PIPE)
    p.wait()
    res = p.communicate()
    res = [res[0], p.returncode]
    return res


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
        self.db = mongoIface()


    def log(self, msg):
        """
        Log specified message to defined logfile.
        """
        self.logf.write('%s %s \n' % (time.strftime('%Y-%m-%d %H:%M:%S'), msg))


    def getPage(self, page, format='text', newAlso=False):
        """
        Get a page from the Howto dir and return it as text/html/twiki.
        """
        if (page and (not page in self.privatePages) 
                and (page.startswith('howto-')) ):

            mydir = howtoDir

            # First see if the text version exists
            # If not, just return nothing (html cannot exist)
            try:
                fname = os.path.join(mydir, page)
#                log('fname = %s' % fname)
                txtTime = os.stat(fname)[-2]

                # If they requested txt, return it, else check html/twiki
                if format in ('html', 'twiki'):

                    if format == 'html':
                        mydirProc = os.path.join(howtoDir, '.html')
                        fnameProc = os.path.join(mydirProc, page + '.html')
    #                    log('fnameProc = %s' % fnameProc)

                    if format == 'twiki':
                        mydirProc = os.path.join(howtoDir, '.twiki')
                        fnameProc = os.path.join(mydirProc, page + '.twiki')

                    # See if the html/twiki version exists
                    # If doesn't exist or is older than txt, create it
                    try:
                        procTime = os.stat(fnameProc)[-2]
                        if procTime < txtTime:
                            raise Exception
                    except:
                        if fname.endswith('.rst'):
                            if format == 'html':
                                out, st = shell(rst2html + ' %s %s > %s' % (fname, page, fnameProc))
                            if format == 'twiki':
                                out, st = shell(rst2twiki + ' %s > %s' % (fname, fnameProc))
                        else:
                            if format == 'html':
                                out, st = shell(txt2html + ' %s > %s' % (fname, fnameProc))
                            else:
                                raise Exception
#                        log('out, st: %s, %s' % (out, st))

                    # Return the html/twiki version
                    fname = fnameProc

                # Return txt/html version
                return fname

            except:
                # The page is not in the 'data' dir, but let's check if it was just added
                # In this case, only text version can be returned (but in the 'data' dir)
                if newAlso and (format == 'text'):  
                    try:
                        fname = os.path.join(newDir, page)
                        txtTime = os.stat(fname)[-2]
                        os.remove(fname)
                        return os.path.join(howtoDir, page)
                    except:
                        pass
                
        # If not found, return None (it means: Error)
        return None


    def checkBodyFilter(self, filter, page):
        """
        """
        if not filter: return True

        fname = os.path.join(howtoDir, page)
        f = open(fname)
        text = f.read()
        f.close()

        for elem in filter:
            if elem and (not re.search(elem, text)): return False

        return True


    def howtoList(self, titleFilter, kwordFilter, bodyFilter):
        """
        Return the list of files in the Howto dir
        """
        text = '<table>'
        cont = 0
        rows = self.db.filter(titleFilter, kwordFilter)
        for row in rows:
            page = row['fname']
            if (not page in self.privatePages):
                if self.checkBodyFilter(bodyFilter, page):
                    page = page.split('howto-')[1]
                    mylink = 'href="howtos2.py?page=howto-%s' % page
                    if (cont % 4) == 0: text += '\n<tr>'
                    text += '\n<td>'
                    text += '<a %s&format=html">%s</a>' % (mylink, page.split('.rst')[0])
                    text += '&nbsp;&nbsp;&nbsp;<br/>'
                    text += '<a class="smLink" %s">txt</a>, &nbsp; ' % mylink
                    text += '<a class="smLink" %s&format=twiki">twiki</a>, &nbsp;' % mylink
                    text += '<a class="smLink" %s&action=edit">edit</a>' % mylink
                    text += '&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;<br/>&nbsp;</td>'
                    if (cont % 4) == 3: text += '\n</tr>' 
                    cont += 1
        text += '\n</table>'

        return text


    def produceIndex(self, titleFilter=[""], kwordFilter=[""], bodyFilter=[""]):
        """
        Produce an index page to look for documents.
        """

        baseTitle = """&nbsp; &nbsp; 
Title filter: <input type="text" class="filter" name="titleFilter" value="%s" autofocus="autofocus"/>"""
        baseKword = """&nbsp; Keyword filter: <input type="text" class="filter" name="kwordFilter" value="%s" />"""
        baseBody = """&nbsp;Contents filter: <input type="text" class="filter" name="bodyFilter" value="%s" />""" 
        
        f = open(iniTempl)
        text = f.read()
        f.close()

        titleText = """<input type="button" value="+" onclick="addTitleFilter()" />"""
        titleText += "<br/>\n&nbsp; &nbsp; ".join([baseTitle % elem  for elem in titleFilter]) 

        kwordText = """<input type="button" value="+" onclick="addKwordFilter()" />"""
        kwordText += "<br/>\n&nbsp; &nbsp; ".join([baseKword % elem  for elem in kwordFilter]) 

  
        bodyText = """<input type="button" value="+" onclick="addBodyFilter()" />"""
        bodyText += "<br/>\n&nbsp; &nbsp; ".join([baseBody % elem  for elem in bodyFilter]) 

        map = {
            'titleFilter': titleText,
            'kwordFilter': kwordText,
            'bodyFilter':  bodyText,
            'list': self.howtoList(titleFilter, kwordFilter, bodyFilter),
        }

        return text % map


    def output(self, page=None, titleFilter=[""], kwordFilter=[""], bodyFilter=[""],
               format='text', action='show'):
        """
        Basic method to display the index page (with appropriate filter) or
        a howto page in the specified format, or even the edition page. 
        """

        # Sanitize filters (at least one filter of each, but by default containing nothing)
        if not titleFilter:  titleFilter = [""]
        elif type(titleFilter) != list:  titleFilter = [titleFilter]

        if not kwordFilter:  kwordFilter = [""]
        elif type(kwordFilter) != list:  kwordFilter = [kwordFilter]

        if not bodyFilter:  bodyFilter = [""]
        elif type(bodyFilter)  != list:   bodyFilter = [bodyFilter]

        # Show index
        if (not page) or (page == 'index.html'):
            self.show(contents=self.produceIndex(titleFilter, kwordFilter, bodyFilter))

        # Show page
        else:
            if action == 'edit': format = 'text'
            htmlPage = self.getPage(page, format)

            if not htmlPage: 
                self.show(ERROR_PAGE, contentsType="text/html")
                return 5

            if action == 'edit':
                self.edit(htmlPage, page) 
            else:
                mytype="text/plain"
                if htmlPage.endswith('.html'):  mytype="text/html"
                self.show(htmlPage, contentsType=mytype, title=page)


    def show(self, fname=None, contents=None, contentsType="text/html", title=""):
        """
        Show contents of the specified file on stdout. Depending on the type of contents,
        the appropriate header is shown before.

        If the contents are of type HTML, we add appropriate links and metadata (we could
        do the same for the other types, with a very lighweight HTML code around the
        text... but I don't like that, if people wants to just download the raw text).
        """
        print "Content-type: %s\n" % contentsType
        if fname:
            if contentsType == "text/html":
                contents = self.showWithMeta(fname, title)
            else:
                f = open(fname)
                contents = f.read()
                f.close()

        # Return the result
        print contents


    def showWithMeta(self, fname, title):
        """
        Insert the top links and the side metadata (keywords, date).
        """
        params = {}
        params['title'] = title

        # Keywords
        params['kwords'] = self.db.nameFilter(title)[0]['kwords']
        params['kwords'] = '\n'.join(['<li>%s</li>' % x for x in params['kwords']])

        # TODO: The change time should be just one more of a list of metadata 
        #       attributes, listed in the mongodb as well
        #       We may also want to show them as a table...
        # Last change
        seconds = os.stat(fname).st_mtime
        params['changeTime'] = time.strftime('%Y-%m-%d %H:%M', time.gmtime(seconds))

        # Scan contents
        f = open(fname)

        # Up to document line
        part = []
        for line in f:
            if not line.startswith('<div class="document" id='): 
                part.append(line)
            else:
                params['docline'] = line
                break
        params['pre'] = ''.join(part)

        # From document line to the end
        part = []
        for line in f:
            if not line.startswith('</body>'): 
                part.append(line)
            else:
                break
        params['most'] = ''.join(part)
        
        f.close()

        # Output results
        return self.showTempl % params


    def edit(self, fname, title='', contents=''):
        """
        Shows an editor page for the specified file name.
        """
        self.log('edit %s, %s' % (fname, title))
        print "Content-type: text/html\n\n"
        if not contents:
            f = open(fname)
            contents = f.read()
            f.close()
#            except IOError as e:
#               if e.errno != 2: raise

        print self.editTempl % {'contents': contents, 'title': title}


    def addHowto(self, pageName):
        """
        Add new howtos page and to mercurial repo.
        """
        fname = self.getPage(pageName, format='text')
        # If the page exists already, abort
        if fname:
            self.show(EXISTING_PAGE)
            return
        os.chdir(newDir)
        title = pageName.split('howto-')[-1].split('.rst')[0]
        sub = '*' * len(title)
        basecontents = BASE_CONTENTS % ({'title': title, 'sub': sub})
#        shell('echo "%s" > %s' % (basecontents, pageName))
        shell("echo '' > %s" % pageName)
        fname = os.path.join(howtoDir, pageName)
        self.edit(fname, pageName, contents=basecontents)


    def save(self, pageName, contents):
        """
        Save the passed contents on the specified page (if it exists)
        and commit into mercurial repo.
        """
        self.log('save %s' % pageName)
        fname = self.getPage(pageName, format='text', newAlso=True)
        if fname:
            f = open(fname, 'w')
            f.write(contents)
            f.close()
            os.chdir(howtoDir)
            out, st = shell("hg ci -A -u howtos.py -m 'Update %s' %s" % (pageName, pageName))
            if st:
                print "Content-type: text/html\n\n"
                print "ERROR %s when saving %s: %s" % (st, pageName, out)
            else:
                print "Content-type: text/html\n\n"
                print "OK"
        else:
            print "Content-type: text/html\n\n"
            print "ERROR when saving %s: can't find page" % (pageName)


    def remoteUpdate(self, pageName, msg="Update"):
        """
        Commit update page into mercurial repo.
        """
        self.log('remoteUpdate %s' % pageName)

        os.chdir(howtoDir)
        out, st = shell("hg ci -A -u howtos.py -m 'Remote - %s' %s" % (msg, pageName))
        if st:
            print "Content-type: text/html\n\n"
            print "ERROR %s when remote-updating %s: %s" % (st, pageName, out)
        else:
            print "Content-type: text/html\n\n"
            print "OK"


### MAIN ### 

# Get cgi values
args = cgi.FieldStorage()
page = args.getvalue('page')
msg  = args.getvalue('msg')
format = args.getvalue('format')
title  = args.getvalue('titleFilter')
kword  = args.getvalue('kwordFilter')
body   = args.getvalue('bodyFilter')
action = args.getvalue('action')
addHowto  = args.getvalue('addHowto')
howtoName = args.getvalue('howtoName')

# Run the main method that returns the html result
howto = howtos()
if addHowto:
    if not howtoName: howto.output(None)
    howto.addHowto('howto-' + howtoName + '.rst')
elif action == 'save':
    contents = args.getvalue('contents')
    howto.save(page, contents)
elif action == 'add':
    contents = args.getvalue('contents')
    howto.add(page, contents)
elif action == 'remoteUpdate':
    howto.remoteUpdate(page, msg)
else:
    howto.output(page, title, kword, body, format, action)
