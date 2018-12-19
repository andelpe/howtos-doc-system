#!/bin/bash

sed 's#.. figure:: /#.. figure:: http://localhost/#' | /usr/bin/rst2pdf --default-dpi=220 "$@" -
