HRU delin QGIS plugin
=====================
Install hru-delin in one click!

What is it?
===========
This plugin is an all-in-one package to easily install and use hru-delin on GNU/Linux and Windows.
It has been tested and works on GNU/Linux and Windows with QGIS 3.8, 3.10 and 3.12.

What can I do with it?
======================
For the moment, the plugin's user interface is very basic. You can load a config file (just like you would do with classic hru-delin) and the plugin will run the 4 steps and load/display result files.
You can select which steps you want to run, in case you just want to run a few steps or you already have intermediate results and you want to finish the job.

How to install ?
================
This plugins includes HRU delin v6.0 and imports it instead of executing it.
This repository has a submodule, this means hru-delin.git repository is nested into hru-delin-qgis.git.
Make sure you clone it like that:

git clone --recurse-submodules --remote-submodules https://forgemia.inra.fr/michael.rabotin/hru-delin.git


Produce a release
Edit version.txt and put the desired version number there.
There are 2 methods to produce a release .zip archive.

Produce locally
You can run ./version.sh and it will produce a zip file ready to be distributed.

Automated release
You can also push to build branch:
git push origin master:build
This will trigger a CI pipeline which will produce a release archive available in the pipeline list as an artifact.
