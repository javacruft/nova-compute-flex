# granite.sh - Devstack extras script to install native lxc

if [[ $VIRT_DRIVER == "granite" ]]; then
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
       source $TOP_DIR/lib/nova_plugins/hypervisor-granite
	   source $TOP_DIR/lib/granite
	   elif [[ $2 == "install" ]] ; then
		  echo_summary "Configuring granite"
		  if is_ubuntu; then
              install_package python-software-properties
              sudo apt-add-repository -y ppa:ubuntu-lxc/daily
              apt_get update
			  install_package --force-yes lxc lxc-dev
              sudo sed -i 's/USE_LXC_BRIDGE.*$/USE_LXC_BRIDGE="false"/' \
				 /etc/default/lxc-net
              mkdir -p ~/.config/lxc
			  echo "lxc.id_map = u 0 100000 65536" > ~/.config/lxc/default.conf
		      echo "lxc.id_map = g 0 100000 65536" >> ~/.config/lxc/default.conf
			  echo "lxc.network.type = veth" >> ~/.config/lxc/default.conf
			  echo "lxc.network.link = lxcbr0" >> ~/.config/lxc/default.conf
			  echo "ubuntu veth lxcbr0 2" | sudo tee -a /etc/lxc/lxc-usernet
			  echo "ubuntu veth br100 2" | sudo tee -a /etc/lxc/lxc-usernet
			  echo "ubuntu veth br-int 2" | sudo tee -a /etc/lxc/lxc-usernet

		  fi
		  install_granite
	fi
fi
