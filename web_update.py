#!/usr/bin/env python
# -*- coding: utf8 -*-
# use for update remote webserver files
# code by chensiyao

import sys,os
import subprocess
import re
import logging
import ConfigParser
import datetime

##定义基础信息
maindir = sys.path[0]
cfgfile = '%s/config/config.cfg' % maindir
logfile = '%s/log/web_update.log' % maindir
now = datetime.datetime.now().strftime('%Y%m%d%H%M')

##定义logging
logging.basicConfig(level=logging.DEBUG,
                format='[%(asctime)s] %(levelname)s %(message)s',
                datefmt='%a, %d %b %Y %H:%M:%S',
                filename=logfile,
                filemode='a')

def GetConfig():
    conf_dic = {}
    conf = ConfigParser.ConfigParser()
    conf.readfp(open(cfgfile))
    global project_list 
    project_list = conf.sections()
    project_list.remove('main') #去掉主模块

    svn_source = '%s/%s' % (maindir, conf.get('main','svn_source'))
    svn_script = '%s/%s' % (maindir, conf.get('main','svn_script'))
    rsync_dir = '%s/%s' % (maindir, conf.get('main','rsync_dir'))
    rsync_host = conf.get('main','rsync_host')
    rsync_key = conf.get('main','rsync_key')
    ssh_key = '%s/%s' % (maindir, conf.get('main','ssh_key'))
    conf_dic = {
	'svn_source': svn_source,
	'svn_script': svn_script,
	'rsync_dir': rsync_dir,
	'rsync_host': rsync_host,
	'rsync_key': rsync_key,
	'ssh_key': ssh_key,
	'modules': {}
    }
    for section in conf.sections():
        if section != 'main':
                try:
			svn_dir = conf.get(section,'svn_dir')
                        hosts = conf.get(section,'hosts').split(',')
                        remote_dir = conf.get(section,'remote_dir')
			excludes = conf.get(section,'excludes').split(',')
			configs = conf.get(section,'configs').split(',')
			version = conf.get(section,'version')
			item = {
				'svn_dir': svn_dir,
				'hosts': hosts,
				'remote_dir': remote_dir,
				'configs': configs,
				'excludes': excludes,
				'version': version
			}
			conf_dic['modules'][section] = item			

                except Exception,e:
                        print e
                        sys.exit(1)

    return conf_dic

def RunShell(cmd):
    logging.info(cmd)
    p = subprocess.Popen(cmd, shell=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    result = p.stdout.readlines()
    retval = p.wait()
    for item in result:
        logging.info(str(item.replace('\n','')))

    if p.returncode != 0:
    	return False
    else:
	    return True

if __name__ == "__main__":
    #获取配置信息
    conf_dic = GetConfig()
    modules = conf_dic['modules']
    #判断传递参数
    if len(sys.argv) == 3:
        module = sys.argv[1]
        version = sys.argv[2]
        if modules.has_key(module) and re.match(r'^\d+$', version):
		try:
			module_dic = conf_dic['modules'][module]
			lastest = module_dic['version']
			if int(version) >= int(lastest):
				logging.info(' --- start pid:%s, module:%s, version: %s --- ' % (os.getpid(), module, version))
				#svn file update
				svn_source = '%s/%s' % (conf_dic['svn_source'], module_dic['svn_dir'])
				svn_script = conf_dic['svn_script']
				cmd = 'sudo -u nobody /bin/sh %s %s %s' % (svn_script, svn_source, version)
				if not RunShell(cmd):
					raise IndexError('svn up faild, try again')
				#copy to syncdir
				rsync_dir = conf_dic['rsync_dir']
				excludes = module_dic['excludes']
				exclude = '--exclude ' + ' --exclude '.join(excludes)
				cmd = '/usr/bin/rsync -vzrtopg --progress --delete %s %s/ %s/%s' % (exclude, svn_source, rsync_dir, module)
				if not RunShell(cmd):
					raise IndexError('copy file faild')
				#modify the config 
				if module_dic['configs'][0]:
					for config in module_dic['configs']:
						full_config = '%s/%s' % (maindir, config)
						if os.path.isfile(full_config):
							cmd = 'chown -R nobody. %s && /usr/bin/rsync -az --delete  %s %s/%s/%s' % (full_config, full_config, rsync_dir, module, config.replace('config/%s/'%module,''))
							if not RunShell(cmd):
								raise IndexError('modify config faild: %s' % full_config)
							else:
								logging.info('modify file %s ok' % full_config)
						else:
							raise IndexError('lose config file %s' % full_config)
				else:
					logging.info('no config file')
				
				#rsync to hosts
				hosts = module_dic['hosts']
				remote_dir = module_dic['remote_dir']
				rsync_host = conf_dic['rsync_host']
                                rsync_key = conf_dic['rsync_key']
                                ssh_key = conf_dic['ssh_key']
				for host in hosts:
					remote_cmd = 'sudo mkdir -p /data/backup/%s && if [ -d "%s" ];then sudo tar acf /data/backup/%s/%s-%s.tar.gz %s; fi && export RSYNC_PASSWORD=\'%s\' && sudo /usr/bin/rsync -vzrtopg --progress webuser@%s::%s %s/' % (module, remote_dir, module, now, module, remote_dir, rsync_key, rsync_host, module, remote_dir)
					cmd = 'ssh -n -i %s -o StrictHostKeyChecking=no -p 22 remoteUser@%s "%s"' % (ssh_key, host, remote_cmd)
					if not RunShell(cmd):
						logging.error('module: %s, host %s, rsync faild' % (module, host))
						print 'module: %s, host %s, rsync faild' % (module, host)
					else:
						print 'module: %s, host %s, rsync success' % (module, host)
				#update the script config
				cf = ConfigParser.ConfigParser()
				cf.read(cfgfile)
				cf.set(module,'version',version)
				fh = open(cfgfile,"w")
				cf.write(fh)
				fh.close()
			
				logging.info(' --- end pid:%s, module:%s, version:%s --- ' % (os.getpid(), module, version))
			else:
				print 'less than lastest version %s' % lastest
				sys.exit(1)

		except Exception as e:
    			print 'error: %s' % e
			sys.exit(1)

	else:
		print "Usge: %s [%s] [revision]" % (sys.argv[0],"|".join(project_list))
      		sys.exit(1)
    else:
        print "Usge: %s [%s] [revision]" % (sys.argv[0],"|".join(project_list))
        sys.exit(0)

