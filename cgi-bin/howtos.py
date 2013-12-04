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
privateHowtos = os.path.join(howtoDir, '.private')
editTempl = os.path.join(BASEDIR, 'edit.templ')

txt2html = CGIDIR + '/simplish.py'
rst2html = CGIDIR + '/txt2html/command.sh'

ERROR_PAGE = os.path.join(BASEDIR, 'error.html')

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


    def getPage(self, page, format = 'text'):
        """
        Get a page from the Howto dir and return it as text/html.
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

                # If they requested txt, return it, else check html
                if format == 'html':
                    mydirHtml = os.path.join(howtoDir, '.html')
                    fnameHtml = os.path.join(mydirHtml, page + '.html')
#                    log('fnameHtml = %s' % fnameHtml)

                    # See if the html version exists
                    # If doesn't exist or is older than txt, create it
                    try:
                        htmlTime = os.stat(fnameHtml)[-2]
                        if htmlTime < txtTime:
                            raise Exception
                    except:
                        if fname.endswith('.rst'):
                            out, st = shell(rst2html + ' %s > %s' % (fname, fnameHtml))
                        else:
                            out, st = shell(txt2html + ' %s > %s' % (fname, fnameHtml))
#                        log('out, st: %s, %s' % (out, st))

                    # Return the html version
                    fname = fnameHtml

                # Return txt/html version
                return fname

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
                if htmlPage.endswith('.html'): 
                    mytype="text/html"
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


    def edit(self, fname, title=''):
        """
        Shows an editor page for the specified file name.
        """
        self.log('edit %s, %s' % (fname, title))
        print "Content-type: text/html\n\n"
        f = open(fname)
        contents = f.read()
        f.close()

        print self.editTempl % {'contents': contents, 'title': title}


    def addHowto(self, pageName):
        """
        Add new howtos page and to mercurial repo.
        """
        os.chdir(howtoDir)
        shell("touch %s" % pageName)
        fname = self.getPage(pageName, format='text')
        if fname:
            self.edit(fname, pageName)


#    def add(self, pageName, contents):
#        """
#        Add new howtos page and to mercurial repo.
#        """
#        fname = os.path.join(howtoDir, pageName)
#        f = open(fname, 'w')
#        f.write(contents)
#        f.close()
#        os.chdir(howtoDir)
#        shell("hg add %s" % pageName)
#        shell("hg ci -u howtos.py -m 'Adding %s' %s" % (pageName, pageName))
#        print "Content-type: text/html\n\n"
#        print "OK"


    def save(self, pageName, contents):
        """
        Save the passed contents on the specified page (if it exists)
        and commit into mercurial repo.
        """
        self.log('save %s' % pageName)
        fname = self.getPage(pageName, format='text')
        if fname:
            f = open(fname, 'w')
            f.write(contents)
            f.close()
            os.chdir(howtoDir)
            shell("hg ci -A -u howtos.py -m 'Update %s' %s" % (pageName, pageName))
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
    howto.addHowto('howto-' + howtoName)
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
