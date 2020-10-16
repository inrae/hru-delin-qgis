#!/bin/bash

git checkout l10n_master
git reset --hard HEAD~100
git pull origin l10n_master
rm -rf /tmp/hru-delin_translation ; cp -r i18n/crowdin /tmp/hru-delin_translation
git checkout master
mv `find /tmp/hru-delin_translation -name "*.ts"` i18n/
rm -rf /tmp/hru-delin_translation
git add i18n
git commit -a -m "get new translations from crowdin"

if [ ! -x /usr/lib/qt5/bin/lrelease ]; then
    echo "please install qttools5-dev-tools package to get 'lrelease' tool"
    exit 1
fi

for i in i18n/*.ts; do
    bn=`basename $i`
    if [[ "$bn" != "hru-delin.ts" ]]; then
        /usr/lib/qt5/bin/lrelease $i
    fi
done
git add i18n

git commit -a -m "process new translations"
