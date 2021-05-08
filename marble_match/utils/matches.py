import logging
import datetime
from typing import Union
from dataclasses import dataclass, field

import discord
from discord.ext import commands

import database.database_operation as database_operation
from database.database_setup import DbHandler
import utils.account as acc
import utils.exception as exception

logger = logging.getLogger(f'marble_match.{__name__}')


@dataclass(order=True)
class Match:
    id: int
    amount: int
    _active: bool
    challenger: acc.Account
    recipient: acc.Account
    _accepted: bool
    _winner: acc.Account = field(default=None)
    _match_time: datetime.datetime = field(default=None)
    _is_history: bool = field(default=False)

    @property
    def active(self) -> bool:
        return self._active

    @active.setter
    def active(self, activity: bool):
        logger.debug(f'active_setter: {activity}')

        # Update active in database, check if write was successful then update Match info
        if database_operation.update_match_activity(DbHandler.db_cnc, self.id, int(activity)):
            self._active = activity
            logger.debug('Updated active')
        else:
            logger.error('Unable to update active')
            raise exception.UnableToWrite

    @property
    def accepted(self) -> bool:
        return self._accepted

    @accepted.setter
    def accepted(self, accepted: bool):
        logger.debug(f'accepted_setter: {accepted}')

        # Update accepted in database, check if write was successful then update Match info
        if database_operation.update_match_accepted(DbHandler.db_cnc, self.id, int(accepted)):
            self._accepted = accepted
            logger.debug('Updated accepted')
        else:
            logger.debug('Unable to update accepted')
            raise exception.UnableToWrite

    @property
    def winner(self) -> acc.Account:
        return self._winner

    @winner.setter
    def winner(self, winner_id: acc.Account):
        logger.debug(f'winner_setter: {winner_id}')
        # Check if winner_id, is either challenger/recipient
        if winner_id == self.challenger or winner_id == self.recipient:
            logger.debug(f'winner_id is equal to challenger or recipient: '
                         f'{winner_id}, {self.challenger}, {self.recipient}')
            self._winner = winner_id
        logger.debug(f'Attempted to change winner_id to invalid id: {self}')

    @property
    def is_history(self) -> bool:
        return self._is_history

    @is_history.setter
    def is_history(self, history: bool):
        logger.debug(f'is_history_setter: {history}')

        # Check if match is already history
        if self._is_history:
            logger.debug(f'Attempted to set is_history flag, when flag is already true')
            return

        # Change history flag
        self._is_history = history

    @property
    def match_time(self) -> datetime.datetime:
        return self._match_time

    @match_time.setter
    def match_time(self, time: datetime.datetime):
        logger.debug(f'match_time_setter: {time}')
        self._match_time = time

    def create_history(self) -> bool:
        logger.debug(f'Create_History: {self}')
        # Check if create_match_history was successful, return True if it was
        if database_operation.create_match_history(DbHandler.db_cnc, self.id, self.amount, self.challenger.id,
                                                   self.recipient.id, self._winner.id, self._match_time):
            logger.debug('Wrote match to match_history')
            # Delete match from table, raise exception if unable to write
            if not database_operation.delete_match(DbHandler.db_cnc, self.id):
                logger.error('Unable to delete match from matches')
                raise exception.UnableToDelete

            return True
        else:
            logger.error('Unable to write to match_history')
            raise exception.UnableToWrite


def create_match(ctx, match_id: int, amount: int, challenger: acc.Account, recipient: acc.Account,
                 active: bool = False, accepted: bool = False) -> Union[Match, int]:
    logger.debug(f'match.create_match: {match_id}, {amount}, {challenger}, {recipient}, {active}, {accepted}')

    # Assuming match_id is None, refill match_id with results of create_match, if zero write was unsuccessful
    match_id = database_operation.create_match(DbHandler.db_cnc, match_id, amount, int(active),
                                               challenger.id, recipient.id)
    logger.debug(f'match_id: {match_id}')

    # Check if match_id is valid (Non zero)
    if not match_id:
        logger.debug('Unable to create match')
        raise exception.UnableToWrite

    # Create Match from match_id, check if match is valid
    match = get_match(ctx, match_id)
    logger.debug(f'match: {match}')
    if not match:
        logger.debug('Unable to create match')
        raise exception.UnableToWrite

    return match


def get_matches_all(ctx, user: acc.Account, user2: acc.Account = None, history: bool = False) -> \
        Union[list[Match], int]:
    """Returns list of all Matches with user

    **Arguments**

    - `<ctx>` Context used to get information
    - `<user>` User who's matches you wish to get
    - `<
    - `<history>` Used to get either match history or active matches

    """
    logger.debug(f'get_matches_all: {user}, {history}')

    # Get all matches with user.id
    matches = database_operation.get_match_info_all(DbHandler.db_cnc, user.id)
    logger.debug(f'matches: {matches}')

    # Check if matches is valid
    if not matches:
        logger.error('matches is zero')
        return 0

    # Create match list to return
    match_list = []

    # Loop through matches and create matches to return
    for match in matches:
        # Get challenger Account and check if valid
        challenger = acc.get_account_from_db(ctx, DbHandler.db_cnc, match[3])
        logger.debug(f'challenger: {challenger}')
        if not challenger:
            logger.error('Unable to get challenger acc')
            return 0

        # Get recipient Account and check if valid
        recipient = acc.get_account_from_db(ctx, DbHandler.db_cnc, match[4])
        logger.debug(f'recipient: {recipient}')
        if not recipient:
            logger.error('Unable to get challenger acc')
            return 0

        # Create match and check if valid before appending to list
        append_match = Match(match[0], match[1], match[2], challenger, recipient, match[5])

        if isinstance(append_match, Match):
            match_list.append(append_match)

    # Check if list has been propagated, return 0 if not
    if not len(match_list):
        logger.debug('match_list length is zero')
        return 0

    # Return matches
    return match_list


def get_match(ctx: commands.Context, match_id: int, history: bool = False) -> Union[Match, int]:
    """Returns Match for Match with match_id

    **Arguments**

    - `<ctx>` Context used to get members and other information
    - `<match_id>` Id of the match to get
    - `<history>` Used to specify if you'd like to get a match from match_history or matches

    """
    logger.debug(f'get_match: {match_id}, {history}')

    # Check if ctx.channel is dm, return zero if true
    if isinstance(ctx.channel, discord.DMChannel):
        logger.error('ctx channel is dm, get_match not allowed in dms')
        return 0

    # Declare match_info to be filled later with tuple of match data from database
    match_info = 0

    # Checks history to decide which table to get match_info from
    if history:
        match_info = database_operation.get_match_history_info(DbHandler.db_cnc, match_id)
    else:
        match_info = database_operation.get_match_info_by_id(DbHandler.db_cnc, match_id)
    logger.debug(f'match_info: {match_info}')

    # Checks if match_info is int, if true return. Is tuple when filled with data
    if isinstance(match_info, int):
        logger.error(f'match_info was type int')
        return 0

    # Check history to get data specific to history matches
    if history:
        # Get Account of challenger
        challenger = acc.get_account_from_db(ctx, DbHandler.db_cnc, match_info[2])
        logger.debug(f'challenger: {challenger}')
        # Checks if challenger is int, if true return 0
        if isinstance(challenger, int):
            logger.error('challenger is type int')
            return 0

        # Get Account of recipient
        recipient = acc.get_account_from_db(ctx, DbHandler.db_cnc, match_info[3])
        logger.debug(f'recipient: {recipient}')
        # Check if recipient is int, if true return 0
        if isinstance(recipient, int):
            logger.error('recipient is type int')
            return 0

        # Get Account for winner
        winner = acc.get_account_from_db(ctx, DbHandler.db_cnc, match_info[4])
        logger.debug(f'winner: {winner}')
        # Checks if winner is int, if true return 0
        if isinstance(winner, int):
            logger.error('winner is type int')
            return 0

        # Create Match with match_info data
        match = Match(match_info[0], match_info[1], True, challenger, recipient, True, winner, match_info[5], True)
        logger.debug(f'match: {match}')
        # Checks if match is type int, if true return 0
        if isinstance(match, int):
            logger.error('match is type int')
            return 0

        # Return match
        return match
    else:
        # Get Account of challenger
        challenger = acc.get_account_from_db(ctx, DbHandler.db_cnc, match_info[3])
        logger.debug(f'challenger: {challenger}')
        # Checks if challenger is int, if true return 0
        if isinstance(challenger, int):
            logger.error('challenger is type int')
            return 0

        # Get Account of recipient
        recipient = acc.get_account_from_db(ctx, DbHandler.db_cnc, match_info[4])
        logger.debug(f'recipient: {recipient}')
        # Check if recipient is int, if true return 0
        if isinstance(recipient, int):
            logger.error('recipient is type int')
            return 0
        # Create match with match_info data
        match = Match(match_info[0], match_info[1], match_info[2], challenger, recipient, match_info[5])

        # Checks if match is type int, if true return 0
        if isinstance(match, int):
            logger.error('match is type int')
            return 0

        # Return match
        return match


def get_matches(ctx, user: acc.Account) -> Union[list[Match], int]:
    logger.debug(f'get_match: {user}')

    # Get matches for Account, check if valid
    match_list = get_matches_all(ctx, user)
    logger.debug(f'match_list: {match_list}')
    if isinstance(match_list, int):
        logger.error('match_list is zero')
        return 0

    # Return match_list
    return match_list
