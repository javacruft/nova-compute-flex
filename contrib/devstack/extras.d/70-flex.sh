# flex.sh - Devstack extras script to install native lxc

if [[ $VIRT_DRIVER == "flex" ]]; then
	if [[ $1 == "source" ]]; then
       # Keep track of the current directory
       SCRIPT_DIR=$(cd $(dirname "$0") && pwd)
       TOP_DIR=$SCRIPT_DIR

       echo $SCRIPT_DIR $TOP_DIR

       # Import common functions
       source $TOP_DIR/functions

       # Load local configuration
       source $TOP_DIR/stackrc

       FILES=$TOP_DIR/files

       # Get our defaults
       source $TOP_DIR/lib/nova_plugins/hypervisor-flex
	   source $TOP_DIR/lib/flex
	   elif [[ $2 == "install" ]] ; then
		  echo_summary "Configuring flex"
		  if is_ubuntu; then
              install_package python-software-properties
              sudo apt-add-repository -y ppa:ubuntu-cloud-archive/juno-staging
              apt_get update
			  install_package --force-yes lxc lxc-dev
              sudo sed -i 's/USE_LXC_BRIDGE.*$/USE_LXC_BRIDGE="false"/' \
				 /etc/default/lxc-net
			  echo "ubuntu veth br100 1000" | sudo tee -a /etc/lxc/lxc-usernet

		  fi
		  install_flex
	fi
fi
