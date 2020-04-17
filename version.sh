#!/bin/bash

if [ -z $version ]; then
	version=`cat version.txt`
fi

rm -rf /tmp/irip
mkdir /tmp/irip
cp -r * /tmp/irip/
cd /tmp
find irip -name "*.pyc" -delete
sed -i 's/^version=.*/version='$version'/' irip/metadata.txt
zip -q -r irip-$version.zip irip
cd -
mv /tmp/irip-$version.zip .
