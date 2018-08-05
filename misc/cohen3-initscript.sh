#!/bin/sh

### BEGIN INIT INFO
# Provides:          cohen3
# Required-Start:    $all
# Required-Stop:     $all
# Default-Start:     2 3 4 5
# Default-Stop:      0 1 6
# Short-Description: Starts or stops the cohen3 mediaserver daemon
# Description:       Put a long description of the service here
### END INIT INFO

NAME=cohen3
DAEMON=/usr/local/bin/${NAME}
CONFIG=/usr/local/etc/${NAME}.conf
LOGFILE=/var/log/${NAME}.log
USER=nobody
DAEMON_OPTS=""
PIDFILE=/var/run/${NAME}.pid
STOP_TIMEOUT=30

# Add any command line options for daemon here

# The process ID of the script when it runs is stored here:

. /lib/lsb/init-functions

do_start () {
    log_daemon_msg "Starting $NAME daemon"
    start-stop-daemon --start --background --pidfile ${PIDFILE} --make-pidfile --user ${USER} --chuid ${USER} --startas ${DAEMON} -- -c ${CONFIG} -l ${LOGFILE} ${DAEMON_OPTS}
    log_end_msg $?
}

do_stop () {
    log_daemon_msg "Stopping $NAME daemon"
    start-stop-daemon --stop --pidfile ${PIDFILE} --retry ${STOP_TIMEOUT}
    log_end_msg $?
}

case "$1" in

    start|stop)
        do_${1}
        ;;

    restart|reload|force-reload)
        do_stop
        do_start
        ;;

    status)
        status_of_proc "$NAME" "$DAEMON" && exit 0 || exit $?
        ;;

    *)
        echo "Usage: /etc/init.d/$NAME {start|stop|restart|status}"
        exit 1
        ;;

esac
exit 0
