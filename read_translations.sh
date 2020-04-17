#!/bin/bash

if [ ! -x /usr/bin/pylupdate5 ]; then
    echo "please install pyqt5-dev-tools package to get 'pylupdate5' tool"
    exit 1
fi

/usr/bin/pylupdate5 *.py -ts i18n/hru-delin.ts
#for i in fr es de it pt el; do
#    pylupdate5 *.py -ts i18n/$i.ts
#done

# use /usr/lib/qt5/bin/linguist to translate
