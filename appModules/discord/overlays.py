# Discord Enhancements Add-on for NVDA
# Overlay classes for enhanced speech output
#
# PERFORMANCE CRITICAL: identify_overlay_class() is called for EVERY
# NVDA object created while Discord is focused.  It MUST be O(1) —
# only checking the object's own immediate properties (role, name).
# NEVER walk parents, siblings, or children here.
#
# The overlays themselves may do more work, because their hooks run only
# when the user actually lands on or reads an object, not when one is
# built.  Keep that work bounded all the same: a person arrowing through
# the member list generates one call per item.
#
# BASE CLASS: these are mixins over NVDAObject, never over a specific
# backend class.  Discord is Chromium, and NVDA represents Chromium
# through IAccessible2 — an overlay deriving from NVDAObjects.UIA.UIA
# would land ahead of IAccessible in the method resolution order and
# every inherited property getter would then look for a UIAElement the
# object does not have.  NVDAObject sits at the end of every MRO, so
# deriving from it overrides exactly what is written below and nothing
# else.

from comtypes import COMError
from logHandler import log
import config
import controlTypes
import ui
from NVDAObjects import NVDAObject
from . import uia


def _verbosity():
	"""Return the configured verbosity level (0 minimal .. 3 extra verbose)."""
	try:
		return config.conf["discordAddon"]["verbosityLevel"]
	except (KeyError, Exception):
		return 1


class _DiscordOverlay(NVDAObject):
	"""Common base for the overlays below.

	Everything here inherits _backendName, which is the only safe way to
	read an object's real name from inside a _get_name override: NVDA fills
	the property cache after the getter returns, so self.name would call
	the getter again and recurse until the stack runs out.  The zero-argument
	super() resolves against this class, and every backend class sits after
	it in the method resolution order, so the call lands on the IAccessible
	(or UIA) getter the object actually came with.
	"""

	def _backendName(self):
		try:
			return super()._get_name() or ""
		except (COMError, AttributeError, Exception):
			return ""


# ---------------------------------------------------------------------------
# Server tree item overlay
# ---------------------------------------------------------------------------

class DiscordServerItem(_DiscordOverlay):
	"""Overlay for server/guild items in the server navigation list.

	Adds the voice indicator the JAWS scripts report while arrowing the
	server tree, so a server with someone in a voice channel is
	distinguishable without opening it.
	"""

	def _get_name(self):
		base = self._backendName()
		if _verbosity() < 1:
			return base
		try:
			if uia.has_voice_activity(self, name=base):
				return base + ", voice active"
		except (COMError, Exception):
			pass
		return base


# ---------------------------------------------------------------------------
# Chat message item overlay
# ---------------------------------------------------------------------------

class DiscordMessageItem(_DiscordOverlay):
	"""Overlay for individual chat messages in the message list.

	Discord usually names the article itself with the whole message, in
	which case this changes nothing.  When it does not — some embeds and
	attachments leave the article unnamed — assemble the text from the
	children rather than letting NVDA report an empty message.
	"""

	def _get_name(self):
		base = self._backendName()
		if base:
			return base
		try:
			return uia.read_message_content(self, name=base, fallback="")
		except (COMError, Exception):
			return base


# ---------------------------------------------------------------------------
# Sectioned list item overlay
# ---------------------------------------------------------------------------

# Discord groups its sidebars under headings -- "Online — 5" in the member
# list, a category name in the channel list.  The heading is a sibling
# rather than an ancestor, so NVDA does not report it on its own.  Track
# the last one announced and speak it only when the section changes;
# repeating it for every item in a long member list would bury the names.
_lastSection = None


class DiscordSectionedListItem(_DiscordOverlay):
	"""Overlay for sidebar items that live under a section heading."""

	#: How far back to look for the heading before giving up.  Each step is
	#: a cross-process sibling lookup, and this runs on every focus change
	#: in a sidebar, so keep it short -- a heading sits directly before the
	#: first item of its section, and the steps past that only help when
	#: Discord slips a separator in between.
	SECTION_SEARCH_LIMIT = 3

	def _findSectionHeading(self):
		prev = self.previous
		attempts = 0
		while prev is not None and attempts < self.SECTION_SEARCH_LIMIT:
			role = uia.safe_role(prev)
			if role in (controlTypes.Role.HEADING, controlTypes.Role.GROUPING):
				return uia.safe_name(prev)
			prev_next = prev.previous
			if prev_next is prev:
				break
			prev = prev_next
			attempts += 1
		return None

	def event_gainFocus(self):
		global _lastSection
		if _verbosity() >= 1:
			try:
				heading = self._findSectionHeading()
				if heading and heading != _lastSection:
					_lastSection = heading
					ui.message(heading)
			except (COMError, Exception):
				log.debugWarning(
					"Discord: section heading lookup failed", exc_info=True)
		super().event_gainFocus()


# ---------------------------------------------------------------------------
# Identification — O(1), no tree walking
# ---------------------------------------------------------------------------

def identify_overlay_class(obj):
	"""Determine which overlay class (if any) should apply to *obj*.

	PERFORMANCE: Only checks obj.role — never walks parents, children, or
	siblings.  Returns None for most objects.
	"""
	try:
		role = obj.role
	except (COMError, AttributeError, Exception):
		return None

	# Discord messages are exposed as articles.
	if role == controlTypes.Role.ARTICLE:
		return DiscordMessageItem

	# The server list is the only tree Discord exposes, so a tree item is
	# a server.  If a future build exposes the channel list as a tree too,
	# the voice indicator is still the right thing to report there.
	if role == controlTypes.Role.TREEVIEWITEM:
		return DiscordServerItem

	# Every sidebar -- channels, DMs, members, forum posts -- is a list of
	# list items grouped under headings.
	if role == controlTypes.Role.LISTITEM:
		return DiscordSectionedListItem

	return None
