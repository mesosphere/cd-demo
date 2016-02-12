FROM mprasil/dokuwiki:latest
ADD start.txt /dokuwiki/data/pages/start.txt
ENTRYPOINT chown www-data:www-data /dokuwiki/data/pages/start.txt && /usr/sbin/lighttpd -D -f /etc/lighttpd/lighttpd.conf
