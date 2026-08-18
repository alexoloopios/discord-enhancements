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

from comtypes import COMError
from logHandler import log
import config
import controlTypes
import ui
from NVDAObjects.UIA import UIA
from . import uia


def _verbosity():
	"""Return the configured verbosity level (0 minimal .. 3 extra verbose)."""
	try:
		return config.conf["discordAddon"]["verbosityLevel"]
	except (KeyError, Exception):
		return 1


# ---------------------------------------------------------------------------
# Server tree item overlay
# ---------------------------------------------------------------------------

class DiscordServerItem(UIA):
	"""Overlay for server/guild items in the server navigation list.

	Adds the voice indicator the JAWS scripts report while arrowing the
	server tree, so a server with someone in a voice channel is
	distinguishable without opening it.
	"""

	def _get_name(self):
		base = uia.base_name(self)
		if _verbosity() < 1:
			return base
		try:
			if uia.has_voice_activity(self):
				return base + ", voice active"
		except (COMError, Exception):
			pass
		return base


# ---------------------------------------------------------------------------
# Chat message item overlay
# ---------------------------------------------------------------------------

class DiscordMessageItem(UIA):
	"""Overlay for individual chat messages in the message list."""

	def _get_name(self):
		return uia.read_message_content(self)


# ---------------------------------------------------------------------------
# Sectioned list item overlay
# ---------------------------------------------------------------------------

# Discord groups its sidebars under headings -- "Online — 5" in the member
# list, a category name in the channel list.  The heading is a sibling
# rather than an ancestor, so NVDA does not report it on its own.  Track
# the last one announced and speak it only when the section changes;
# repeating it for every item in a long member list would bury the names.
_lastSection = None


class DiscordSectionedListItem(UIA):
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
