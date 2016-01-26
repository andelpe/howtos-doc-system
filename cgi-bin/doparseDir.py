#!/usr/bin/env python

#from mongoIface import mongoIface   
#db = mongoIface()           
#db.parseDir('/var/www/html/howtos')


from elasticIface import ElasticIface
db = ElasticIface(verb=True)
db.parseDir('/var/www/html/howtos')

