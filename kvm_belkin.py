#!/usr/bin/env python3

import bs4 as BeautifulSoup
import collections
import os
import os.path
import requests
import subprocess
import sys
import urllib3

if len(sys.argv) != 4:
    print("%s <user> <password> <ip address>" % (sys.argv[0],))
    sys.exit(1)
user = sys.argv[1]
pswd = sys.argv[2]
host = sys.argv[3]

# Silence SSL Certification warnings
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# Start a requests Session to have persistent cookies
s = requests.Session()
s.headers.update(
    {
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10.14; rv:63.0) Gecko/20100101 Firefox/63.0",
        "Accept-Language": "en-US,en;q=0.5",
    }
)
s.verify = False

# Grab login page
s.get("http://%s/auth.asp" % (host,))

# Login
data = collections.OrderedDict(
    [
        ("action_login.x", 12),
        ("action_login.y", 12),
        ("login", user),
        ("nickname", ""),
        ("password", pswd),
    ]
)
r = s.post(
    "http://%s/auth.asp" % (host,),
    headers={"Referer": "http://%s/auth.asp" % (host,)},
    data=data,
)

# Verify we correctly authenticated
assert "Authenticate with Login and Password" not in r.text

# Download the applet page
r = s.get(
    "http://%s/title_app.asp" % (host,),
    headers={"Referer": "http://%s/auth.asp" % (host,)},
)
# Verify we actually got some data
assert len(r.text) > 0
soup = BeautifulSoup.BeautifulSoup(r.text, "html.parser")

orig_port = None
redir_port = 4443

params = {
    "REAL_HOST": host,
    "HOTKEYNAME_0": "Ctrl+Alt+Delete",
    "SOFTKBD_MAPPING": "en",
    "EXCLUSIVE_MOUSE": False,
    "LOCAL_CURSOR": False,
    "PORT": redir_port,
    "SSLPORT": redir_port,
    "PORT_ID": redir_port,
    "CLUSTER_PORT_ID": redir_port,
    "VS_TYPE": "no",
    "logo": False,
    "logo_off": "no",
}

for p in soup.find_all("param"):
    if p["name"] in ["PORT", "SSLPORT"]:
        orig_port = p["value"]
    try:
        p["value"] = params[p["name"]]
    except KeyError:
        pass

# Hacks for when "use Sun Java" is enabled
if 'embed' in soup:
    embed = soup("embed")[0]
    embed['port'] = params['PORT']
    embed['port_id'] = params['PORT_ID']
    embed['sslport'] = params['SSLPORT']
    embed['logo'] = False
    embed['logo_off'] = 'no'
    soup("embed")[0]["archive"] = soup("embed")[0]["cache_archive"]

    jars = [x.strip() for x in soup("embed")[0]["cache_archive"].replace(",", " ").split()]
else:
    jars = [x.strip() for x in soup("applet")[0]["archive"].replace(",", " ").split()]


# save the fixed viewer.html
with open("viewer.html", "w") as f:
    f.write(soup.prettify())

# download the jars
for jar in jars:
    r = s.get(
        "http://%s/%s" % (host, jar),
        headers={"Referer": "http://%s/title_app.asp" % (host,)},
    )
    assert len(r.text) > 0
    with open(jar, "wb") as f:
        f.write(r.content)

# Write out temporary weak java security settings. Just to make sure we're not breaking on old KVM viewers
with open("java.security", "w") as f:
    f.write(
        """jdk.certpath.disabledAlgorithms=
jdk.jar.disabledAlgorithms=
jdk.tls.disabledAlgorithms=
jdk.tls.legacyAlgorithms= \
        K_NULL, C_NULL, M_NULL, \
        DHE_DSS_EXPORT, DHE_RSA_EXPORT, DH_anon_EXPORT, DH_DSS_EXPORT, \
        DH_RSA_EXPORT, RSA_EXPORT, \
        DH_anon, ECDH_anon, \
        RC4_128, RC4_40, DES_CBC, DES40_CBC, \
        3DES_EDE_CBC"""
    )
with open("java.policy", "w") as f:
    f.write(
        """grant {
   permission java.security.AllPermission;
};"""
    )

# Start port redirection
redirect = subprocess.Popen(
    [
        "socat",
        "TCP-LISTEN:%s,fork,reuseaddr" % (redir_port,),
        "TCP:%s:%s" % (host, orig_port),
    ]
)

# Start javaws viewer
subprocess.call(
    [
        "appletviewer",
        "-J-Djava.security.properties=java.security",
        "-J-Djava.security.policy=java.policy",
        "viewer.html",
    ]
)

# Stop port redirection
redirect.kill()

# Remove our temporary files
os.remove("viewer.html")
os.remove("java.security")
os.remove("java.policy")
for jar in jars:
    os.remove(jar)


# Logout
r = s.post(
    "http://%s/logout" % (host,), headers={"Referer": "http://%s/auth.asp" % (host,)}
)
