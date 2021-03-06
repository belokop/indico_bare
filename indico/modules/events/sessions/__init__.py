# This file is part of Indico.
# Copyright (C) 2002 - 2016 European Organization for Nuclear Research (CERN).
#
# Indico is free software; you can redistribute it and/or
# modify it under the terms of the GNU General Public License as
# published by the Free Software Foundation; either version 3 of the
# License, or (at your option) any later version.
#
# Indico is distributed in the hope that it will be useful, but
# WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the GNU
# General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with Indico; if not, see <http://www.gnu.org/licenses/>.

from __future__ import unicode_literals

from operator import itemgetter

from flask import flash, session, render_template
from wtforms import BooleanField

from indico.core import signals
from indico.core.logger import Logger
from indico.core.roles import ManagementRole, check_roles
from indico.modules.events.sessions.models.sessions import Session
from indico.modules.events.sessions.util import get_sessions_for_user
from indico.modules.events.settings import EventSettingsProxy
from indico.util.i18n import _, ngettext
from indico.web.flask.templating import template_hook
from indico.web.flask.util import url_for
from indico.web.forms.base import IndicoForm, FormDefaults
from indico.web.forms.widgets import SwitchWidget
from indico.web.menu import SideMenuItem


logger = Logger.get('events.sessions')
session_settings = EventSettingsProxy('sessions', {
    # Whether session coordinators can manage contributions inside their sessions
    'coordinators_manage_contributions': False,
    # Whether session coordinators can manage their session blocks
    'coordinators_manage_blocks': False
})


COORDINATOR_PRIV_SETTINGS = {'manage-contributions': 'coordinators_manage_contributions',
                             'manage-blocks': 'coordinators_manage_blocks'}
COORDINATOR_PRIV_TITLES = {'manage-contributions': _('Contributions'),
                           'manage-blocks': _('Session blocks')}
COORDINATOR_PRIV_DESCS = {'manage-contributions': _('Allows coordinators to modify contributions in their sessions.'),
                          'manage-blocks': _('Allows coordinators to manage/reschedule session blocks of their '
                                             'sessions.  This includes creating new session blocks..')}


@signals.users.merged.connect
def _merge_users(target, source, **kwargs):
    from indico.modules.events.sessions.models.principals import SessionPrincipal
    SessionPrincipal.merge_users(target, source, 'session')


@signals.users.registered.connect
@signals.users.email_added.connect
def _convert_email_principals(user, **kwargs):
    from indico.modules.events.sessions.models.principals import SessionPrincipal
    sessions = SessionPrincipal.replace_email_with_user(user, 'session')
    if sessions:
        num = len(sessions)
        flash(ngettext("You have been granted manager/coordination privileges for a session.",
                       "You have been granted manager/coordination privileges for {} sessions.", num).format(num),
              'info')


@signals.menu.items.connect_via('event-management-sidemenu')
def _extend_event_management_menu(sender, event, **kwargs):
    if not event.can_manage(session.user, allow_key=True):
        return
    if event.type == 'conference':
        return SideMenuItem('sessions', _('Sessions'), url_for('sessions.session_list', event), section='organization')


@template_hook('conference-protection')
def _inject_conference_protection_coordinator_privs(event, **kwargs):
    settings = session_settings.get_all(event)
    form_class = type(b'PrivsForm', (IndicoForm,), {})
    defaults = {}
    for name, title in sorted(COORDINATOR_PRIV_TITLES.iteritems(), key=itemgetter(1)):
        field = BooleanField(title, widget=SwitchWidget(), description=COORDINATOR_PRIV_DESCS[name])
        setattr(form_class, name, field)
        defaults[name] = settings[COORDINATOR_PRIV_SETTINGS[name]]
    form = form_class(csrf_enabled=False, obj=FormDefaults(defaults))
    return render_template('events/sessions/management/coordinator_privs.html', event=event, form=form)


@signals.event_management.get_cloners.connect
def _get_session_cloner(sender, **kwargs):
    from indico.modules.events.sessions.clone import SessionCloner
    return SessionCloner


@signals.app_created.connect
def _check_roles(app, **kwargs):
    check_roles(Session)


@signals.acl.get_management_roles.connect_via(Session)
def _get_management_roles(sender, **kwargs):
    return CoordinatorRole


class CoordinatorRole(ManagementRole):
    name = 'coordinate'
    friendly_name = _('Coordination')
    description = _('Grants coordination access to the session.')


@signals.event.sidemenu.connect
def _extend_event_menu(sender, **kwargs):
    from indico.modules.events.layout.util import MenuEntryData

    def _visible_my_sessions(event):
        return session.user and bool(get_sessions_for_user(event.as_event, session.user))

    yield MenuEntryData(title=_("My Sessions"), name='my_sessions', endpoint='sessions.my_sessions', position=1,
                        parent='my_conference', visible=_visible_my_sessions)
