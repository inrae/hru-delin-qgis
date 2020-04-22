#!/bin/bash

if [ -z $version ]; then
	version=`cat version.txt`
fi

rm -f hrudelin*.zip
rm -rf /tmp/hrudelin
mkdir /tmp/hrudelin
cp -r * /tmp/hrudelin/
cd /tmp
rm -f hrudelin/*.sh hrudelin/version.txt
find hrudelin -name "*.pyc" -delete
find hrudelin -name "__pycache__" -delete
sed -i 's/^version=.*/version='$version'/' hrudelin/metadata.txt
zip -q -r hrudelin-$version.zip hrudelin
cd -
mv /tmp/hrudelin-$version.zip .
