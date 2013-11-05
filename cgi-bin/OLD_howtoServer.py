#!/usr/bin/env python

#from __future__ import division, print_function


### IMPORTS ###
import cherrypy 
from cherrypy.lib.static import serve_file
import os, logging
import re
import subprocess as sub


### CONSTANTS ####
BASEDIR = '/home/delgadop/work/servers/howtos'
howtoDir = os.path.join(BASEDIR, 'data/howtos')
privateHowtos = os.path.join(howtoDir, '.private')
INIT_PAGE = os.path.join(BASEDIR, 'index.html')
ERROR_PAGE = os.path.join(BASEDIR, 'error.html')

#txt2html = 'txt2html --indent_par_break --preserve_indent --par_indent 1 --short_line_length 150'
txt2html = BASEDIR + '/utils/simplish.py'


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


def log(msg, level = logging.DEBUG):
    """
    Logs to cherrypy log files.
    """
    cherrypy.log(msg, severity=level)


### CHERRYPY CLASS ### 
class HowToTree(object): 
    
    def __init__(self):
        """
        Constructor. Initialize the private pages variable.
        """
        f = open(privateHowtos)
        lines = f.readlines()
        f.close()

        self.privatePages = [x.strip() for x in lines]
        log('Private pages: %s ' % self.privatePages, level = logging.INFO)


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
                if (not titleFilter) or (re.search(titleFilter, page)):
                    if self.checkBodyFilter(bodyFilter, page):
                        text += '\n<br/><li> %s: &nbsp; ' % page
                        text += '<a href="/howto/%s">txt</a>, &nbsp; ' % page
                        text += '<a href="/howto/%s?format=html">' % page
                        text += 'html</a> </li>' 
        text += '\n</ul>'

        return text


    def produceIndex(self, titleFilter = None, bodyFilter = None):
        """
        Produce an index page to look for documents.
        """

        text = """
<html>
<body>

<br/><br/><br/><br/>

<table>
<tr>
<td width="40%%"></td>

<td width="60%%">
<form action="/howto/index.html" method="get">
  &nbsp;&nbsp;&nbsp; Title filter: &nbsp;&nbsp;&nbsp; <input type="text" name="titleFilter" />  
  &nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;
  <input type="submit" value="Apply" />
  <br/>
  Contents filter: <input type="text" name="bodyFilter" />  
  <br/>
</form> 

<br/>

%s

</td></tr>
</table>

</body>
</html>
    """ % (self.howtoList(titleFilter, bodyFilter))

        return text


    def howto(self, page = None, titleFilter = None, bodyFilter = None,
              format = 'text'):

        if (not page) or (page == 'index.html'):
            return self.produceIndex(titleFilter, bodyFilter) 

        else:
            htmlPage = self.getPage(page, format)

            if not htmlPage:
                htmlPage = ERROR_PAGE

            if htmlPage.endswith('.html'):
                return serve_file(htmlPage, "text/html")
            else:
                return serve_file(htmlPage, "text/plain")



    def index(self, page = None):  
        if (not page) or (page == 'index.html'):
            return serve_file(INIT_PAGE, "text/html")
        else:
            return serve_file(ERROR_PAGE, "text/html")

    howto.exposed = True
    index.exposed = True 



### MAIN ### 
opts = {'server.socket_port': 5080, 
        'server.socket_host': '0.0.0.0' 
       } 
cherrypy.config.update(opts)
cherrypy.quickstart(HowToTree())

