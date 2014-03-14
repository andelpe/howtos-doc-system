#!/usr/bin/env python

#from __future__ import division, print_function


### IMPORTS ###
import os, logging, time
import re
import subprocess as sub
import cgi


### CONSTANTS ####
BASEDIR = '/var/www/html/howtos'
CGIDIR = '/var/www/cgi-bin/howtos'
howtoDir = os.path.join(BASEDIR, 'data')
newDir = os.path.join(BASEDIR, 'new')
privateHowtos = os.path.join(howtoDir, '.private')
editTempl = os.path.join(BASEDIR, 'edit.templ')

txt2html = CGIDIR + '/simplish.py'
rst2html = CGIDIR + '/txt2html/command.sh'
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

        f = open(editTempl)
        self.editTempl = f.read()
        f.close()

        self.logf = open(logfile, 'a')


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
        return re.search(filter, text)


    def howtoList(self, titleFilter, bodyFilter):
        """
        Return the list of files in the Howto dir
        """
        text = '<ul>'
        for page in sorted(os.listdir(howtoDir)):
            if (not page in self.privatePages) and (page.startswith('howto-')):
                if (not titleFilter) or (re.search("howto-.*"+titleFilter, page)):
                    if self.checkBodyFilter(bodyFilter, page):
                        text += '\n<br/><li> '
                        text += '<a href="howtos.py?page=%s&format=html">%s</a> &nbsp; (' % (page, page)
                        text += '<a href="howtos.py?page=%s">txt</a>, &nbsp; ' % page
                        text += '<a href="howtos.py?page=%s&format=twiki">twiki</a>, &nbsp;' % page
                        text += '<a href="howtos.py?page=%s&action=edit">edit</a>)' % page
                        text += ' </li>' 
        text += '\n</ul>'

        return text


    def produceIndex(self, titleFilter = None, bodyFilter = None):
        """
        Produce an index page to look for documents.
        """

        text = """
<html>
<head>
 <style type="text/css">
 .filter{
 background-color: LightGreen;
 }
 .add{
 background-color: Orange;
 }
 </style>
</head>
<body>

<br/><br/>
<center><h1>HowTo's&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;</h1></center>
<br/><br/>

<table>
<tr>
<td width="25%%"></td>

<td width="40%%">
<form action="howtos.py" method="get">
  &nbsp;&nbsp;&nbsp; Title filter: &nbsp;&nbsp; <input type="text" class="filter" name="titleFilter" />  
  &nbsp;&nbsp;&nbsp;&nbsp;&nbsp;
  <input type="submit" name="filter" class="filter" value="Apply filter" />
  <br/>
  Contents filter: <input type="text" class="filter" name="bodyFilter" />  
</form> 
</td>

<td width="5%%"></td>

<td width="20%%">
<form action="howtos.py" method="get">
  <center>
  <input type="submit" name="addHowto" class="add" value="Add Howto:" />
  <br/><br/>
  &nbsp;&nbsp;
  howto-<input type="text" class="add" name="howtoName" />
  </center>
</form>
</td>
<td width="10%%"></td>
</tr>

<tr>
<td></td>
<td>
%s
</td>
</tr>
</table>

</body>
</html>
        """ % (self.howtoList(titleFilter, bodyFilter))

        return text


    def output(self, page = None, titleFilter = None, bodyFilter = None,
               format = 'text', action='show'):
        """
        Basic method to display the index page (with appropriate filter) or
        a howto page in the specified format, or even the edition page. 
        """

        if (not page) or (page == 'index.html'):
            self.show(contents=self.produceIndex(titleFilter, bodyFilter))

        else:
            if action == 'edit': format = 'text'
            htmlPage = self.getPage(page, format)

            if not htmlPage: htmlPage = ERROR_PAGE

            if action == 'edit':
                self.edit(htmlPage, page) 
            else:
                mytype="text/plain"
                if htmlPage.endswith('.html'):  mytype="text/html"
                self.show(htmlPage, contentsType=mytype)


    def show(self, fname=None, contents=None, contentsType="text/html"):
        """
        Show contents of the specified file on stdout. Depending on the type of contents,
        the appropriate header is shown before.
        """
        print "Content-type: %s\n" % contentsType
        if fname:
            f = open(fname)
            contents = f.read()
            f.close()
        print contents


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


    def remoteUpdate(self, pageName):
        """
        Commit update page into mercurial repo.
        """
        self.log('remoteUpdate %s' % pageName)
        fname = self.getPage(pageName, format='text')
        if fname:
            os.chdir(howtoDir)
            out, st = shell("hg ci -A -u howtos.py -m 'Remote update %s' %s" % (pageName, pageName))
            if st:
                print "Content-type: text/html\n\n"
                print "ERROR %s when remote-updating %s: %s" % (st, pageName, out)
            else:
                print "Content-type: text/html\n\n"
                print "OK"
        else:
            print "Content-type: text/html\n\n"
            print "ERROR when remote-updating %s: can't find page" % (pageName)



### MAIN ### 

# Get cgi values
args = cgi.FieldStorage()
page = args.getvalue('page')
format = args.getvalue('format')
title = args.getvalue('titleFilter')
body = args.getvalue('bodyFilter')
action = args.getvalue('action')
addHowto = args.getvalue('addHowto')
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
    howto.remoteUpdate(page)
else:
    howto.output(page, title, body, format, action)
