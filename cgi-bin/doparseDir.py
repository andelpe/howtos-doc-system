#!/usr/bin/env python

from mongoIface import mongoIface   
db = mongoIface()           
db.parseDir('/var/www/html/howtos')
