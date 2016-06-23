# -*- coding: utf-8 -*-
#-------------------------------------------------------------------------#
#   Copyright (C) 2010 by Christoph Thelen                                #
#   doc_bacardi@users.sourceforge.net                                     #
#                                                                         #
#   This program is free software; you can redistribute it and/or modify  #
#   it under the terms of the GNU General Public License as published by  #
#   the Free Software Foundation; either version 2 of the License, or     #
#   (at your option) any later version.                                   #
#                                                                         #
#   This program is distributed in the hope that it will be useful,       #
#   but WITHOUT ANY WARRANTY; without even the implied warranty of        #
#   MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the         #
#   GNU General Public License for more details.                          #
#                                                                         #
#   You should have received a copy of the GNU General Public License     #
#   along with this program; if not, write to the                         #
#   Free Software Foundation, Inc.,                                       #
#   59 Temple Place - Suite 330, Boston, MA  02111-1307, USA.             #
#-------------------------------------------------------------------------#


import imp
import os
import re
import subprocess
import sys

from SCons.Script import *


# Import all local modules.
import archive
import artifact
import artifact_version
import bootblock
import build_properties
import data_array
import diff
import flex_zip
import gcc_symbol_template
import gen_random_seq
import hash
import hboot_image
import hexdump
import objimport
import svnversion
import uuencode
import version
import xsl_transform



#----------------------------------------------------------------------------
#
# Accept 'clean' target like make as an alternative to '-c'. This makes it
# much easier to work with an IDE like KDevelop.
#
if 'clean' in COMMAND_LINE_TARGETS:
	Alias('clean', SCons.Node.FS.get_default_fs().SConstruct_dir.abspath)
	SetOption('clean', 1)


#----------------------------------------------------------------------------
#
# Display the complete command line if any command failed.
#
# TODO: GetBuildFailures only reports scons errors. If an exception occured,
#       this list is empty and the function reports a successful build right
#       after the stack dump. How can I detect this here?
#
def display_build_status():
	from SCons.Script import GetBuildFailures
	bf_all = GetBuildFailures()
	if bf_all:
		# iterate over all failures and print the command
		for bf in bf_all:
			if bf and bf.node and bf.command:
				print 'Failed command for ' + str(bf.node) + ":\n" + ' '.join(bf.command)
		print "!!!!!!!!!!!!!!!"
		print "!!! FAILED !!!!"
		print "!!!!!!!!!!!!!!!"

import atexit
atexit.register(display_build_status)



def find_first_tool(strToolPattern):
	global TOOLS
	strToolName = None

	tPattern = re.compile(strToolPattern)
	for strKey in TOOLS.iterkeys():
		tMatch = re.search(tPattern, strKey)
		if not tMatch is None:
			strToolName = strKey
			break

	return strToolName



def get_tool(env, strToolName):
	global TOOLS

	tMod = None
	try:
		strPath = TOOLS[strToolName]
		strModulName = strToolName.replace('-','_').replace('.','_')
		fp,pathname,description = imp.find_module(strModulName, [strPath])
		try:
			tMod = imp.load_module(strModulName, fp, pathname, description)
		finally:
			# Since we may exit via an exception, close fp explicitly.
			if fp:
				fp.close()
	except KeyError:
		pass

	if tMod==None:
		raise Exception(strToolName, 'The requested tool is not part of the configuration. Add it to setup.xml and rerun mbs.')

	return tMod



def CreateEnvironment(env=None, strGccPattern=None, astrGccFlags=None, strAsciiDocPattern=None):
	astrDefaultGccFlags = Split("""
		-ffreestanding
		-mlong-calls
		-Wall
		-Wextra
		-Wconversion
		-Wshadow
		-Wcast-qual
		-Wwrite-strings
		-Wcast-align
		-Wpointer-arith
		-Wmissing-prototypes
		-Wstrict-prototypes
		-g3
		-gdwarf-2
		-std=c99
		-pedantic
	""")

	# Create the new environment.
	env = Environment()
	env.Decider('MD5')

	if strGccPattern!=None:
		strGccId = find_first_tool(strGccPattern)
		if strGccId is None:
			raise Exception('No match found searching for a compiler matching the pattern "%s".' % strGccPattern)
		if astrGccFlags is None:
			astrGccFlags = astrDefaultGccFlags
		add_tool_to_environment(env, strGccId)
		env.Replace(CCFLAGS = Split(astrGccFlags))
		env.Replace(LIBS = ['m', 'c', 'gcc'])
		env.Replace(LINKFLAGS = ['--gc-sections', '-nostdlib', '-static'])

	if strAsciiDocPattern!=None:
		strAsciiDocId = find_first_tool(strAsciiDocPattern)
		if strAsciiDocId is None:
			raise Exception('No match found searching for AsciiDoc matching the pattern "%s".' % strAsciiDocPattern)
		add_tool_to_environment(env, strAsciiDocId)

	archive.ApplyToEnv(env)
	artifact.ApplyToEnv(env)
	artifact_version.ApplyToEnv(env)
	bootblock.ApplyToEnv(env)
	build_properties.ApplyToEnv(env)
	data_array.ApplyToEnv(env)
	diff.ApplyToEnv(env)
	flex_zip.ApplyToEnv(env)
	gcc_symbol_template.ApplyToEnv(env)
	gen_random_seq.ApplyToEnv(env)
	hash.ApplyToEnv(env)
	hboot_image.ApplyToEnv(env)
	hexdump.ApplyToEnv(env)
	objimport.ApplyToEnv(env)
	ApplyToEnv(env)
	svnversion.ApplyToEnv(env)
	uuencode.ApplyToEnv(env)
	version.ApplyToEnv(env)
	xsl_transform.ApplyToEnv(env)

	return env



def add_tool_to_environment(env, strToolIdAndVersion):
	tTool = get_tool(env, strToolIdAndVersion)
	tTool.ApplyToEnv(env)



def set_build_path(env, build_path, source_path, sources):
	# Convert the sources to a list.
	if isinstance(sources, str):
		sources = Split(sources)
	env.VariantDir(build_path, source_path, duplicate=0)
	return [src.replace(source_path, build_path) for src in sources]


def create_compiler_environment(env, strAsicTyp, aAttributes):
	# Find the library paths for gcc and newlib.

	# Prepend an 'm' to each attribute and create a set from this list.
	aMAttributes = set(['m'+strAttr for strAttr in aAttributes])

	# Prepend an '-m' to each attribute.
	aOptAttributes = ['-m'+strAttr for strAttr in aAttributes]

	# Get the mapping for multiple library search directories.
	strMultilibPath = None
	aCmd = [env['CC']]
	aCmd.extend(aOptAttributes)
	aCmd.append('-print-multi-lib')
	proc = subprocess.Popen(aCmd, stdout=subprocess.PIPE)
	strOutput = proc.communicate()[0]
	for match_obj in re.finditer('^([^;]+);@?([^\r\n\t ]+)', strOutput, re.MULTILINE):
		strPath = match_obj.group(1)
		aAttr = set(match_obj.group(2).split('@'))
		if aAttr==aMAttributes:
			strMultilibPath = strPath
			break

	if strMultilibPath==None:
		raise Exception('Could not find multilib configuration for attributes %s' % (','.join(aAttributes)))

	strGccLibPath = os.path.join(env['GCC_LIBRARY_DIR_COMPILER'], strMultilibPath)
	strNewlibPath = os.path.join(env['GCC_LIBRARY_DIR_ARCHITECTURE'], strMultilibPath)

	env_new = env.Clone()
	env_new.Append(CCFLAGS = aOptAttributes)
	env_new.Replace(LIBPATH = [strGccLibPath, strNewlibPath])
	env_new.Append(CPPDEFINES = [['ASIC_TYP', '%s'%strAsicTyp]])

	return env_new


def ApplyToEnv(env):
	env.AddMethod(set_build_path, 'SetBuildPath')
	env.AddMethod(create_compiler_environment, 'CreateCompilerEnv')
	env.AddMethod(get_tool, 'GetTool')
	env.AddMethod(CreateEnvironment, "CreateEnvironment")
