#!/bin/bash

set -xe

env

NOVAGRANITEDIR=$(readlink -f $(dirname $0)/../..)
INSTALLDIR=${INSTALLDIR:-/opt/stack}

cp $NOVAGRANITEDIR/contrib/devstack/extras.d/70-flex.sh $INSTALLDIR/devstack/extras.d
cp $NOVAGRANITEDIR/contrib/devstack/lib/nova_plugins/hypervisor-flex $INSTALLDIR/devstack/lib/nova_plugins/
cp $NOVAGRANITEDIR/contrib/devstack/lib/flex $INSTALLDIR/devstack/lib/flex
cat - <<-EOF >> $INSTALLDIR/devstack/localrc
VIRT_DRIVER=flex
EOF
