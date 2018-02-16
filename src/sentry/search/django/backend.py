"""
sentry.search.django.backend
~~~~~~~~~~~~~~~~~~~~~~~~~~~~

:copyright: (c) 2010-2014 by the Sentry Team, see AUTHORS for more details.
:license: BSD, see LICENSE for more details.
"""

from __future__ import absolute_import

from collections import namedtuple

from django.db import router
from django.db.models import Q

from sentry import tagstore
from sentry.api.paginator import DateTimePaginator, Paginator
from sentry.search.base import EMPTY, SearchBackend
from sentry.search.django.constants import (
    MSSQL_ENGINES, MSSQL_SORT_CLAUSES, MYSQL_SORT_CLAUSES, ORACLE_SORT_CLAUSES, SORT_CLAUSES,
    SQLITE_SORT_CLAUSES
)
from sentry.utils.db import get_db_engine
from sentry.utils.dates import to_timestamp


class DjangoSearchBackend(SearchBackend):
    def _build_queryset(
        self,
        project,
        query=None,
        status=None,
        tags=None,
        bookmarked_by=None,
        assigned_to=None,
        first_release=None,
        sort_by='date',
        unassigned=None,
        subscribed_by=None,
        age_from=None,
        age_from_inclusive=True,
        age_to=None,
        age_to_inclusive=True,
        last_seen_from=None,
        last_seen_from_inclusive=True,
        last_seen_to=None,
        last_seen_to_inclusive=True,
        date_from=None,
        date_from_inclusive=True,
        date_to=None,
        date_to_inclusive=True,
        active_at_from=None,
        active_at_from_inclusive=True,
        active_at_to=None,
        active_at_to_inclusive=True,
        times_seen=None,
        times_seen_lower=None,
        times_seen_lower_inclusive=True,
        times_seen_upper=None,
        times_seen_upper_inclusive=True,
        cursor=None,
        limit=None,
        environment_id=None,
    ):
        from sentry.models import Event, Group, GroupSubscription, GroupStatus

        engine = get_db_engine('default')

        queryset = Group.objects.filter(project=project)

        if query:
            # TODO(dcramer): if we want to continue to support search on SQL
            # we should at least optimize this in Postgres so that it does
            # the query filter **after** the index filters, and restricts the
            # result set
            queryset = queryset.filter(
                Q(message__icontains=query) | Q(culprit__icontains=query))

        if status is None:
            status_in = (
                GroupStatus.PENDING_DELETION, GroupStatus.DELETION_IN_PROGRESS,
                GroupStatus.PENDING_MERGE,
            )
            queryset = queryset.exclude(status__in=status_in)
        else:
            queryset = queryset.filter(status=status)

        if bookmarked_by:
            queryset = queryset.filter(
                bookmark_set__project=project,
                bookmark_set__user=bookmarked_by,
            )

        if assigned_to:
            queryset = queryset.filter(
                assignee_set__project=project,
                assignee_set__user=assigned_to,
            )
        elif unassigned in (True, False):
            queryset = queryset.filter(
                assignee_set__isnull=unassigned,
            )

        if subscribed_by is not None:
            queryset = queryset.filter(
                id__in=GroupSubscription.objects.filter(
                    project=project,
                    user=subscribed_by,
                    is_active=True,
                ).values_list('group'),
            )

        if first_release:
            if first_release is EMPTY:
                return queryset.none()
            queryset = queryset.filter(
                first_release__organization_id=project.organization_id,
                first_release__version=first_release,
            )

        if tags:
            matches = tagstore.get_group_ids_for_search_filter(project.id, environment_id, tags)
            if not matches:
                return queryset.none()
            queryset = queryset.filter(
                id__in=matches,
            )

        if age_from or age_to:
            params = {}
            if age_from:
                if age_from_inclusive:
                    params['first_seen__gte'] = age_from
                else:
                    params['first_seen__gt'] = age_from
            if age_to:
                if age_to_inclusive:
                    params['first_seen__lte'] = age_to
                else:
                    params['first_seen__lt'] = age_to
            queryset = queryset.filter(**params)

        if last_seen_from or last_seen_to:
            params = {}
            if last_seen_from:
                if last_seen_from_inclusive:
                    params['last_seen__gte'] = last_seen_from
                else:
                    params['last_seen__gt'] = last_seen_from
            if last_seen_to:
                if last_seen_to_inclusive:
                    params['last_seen__lte'] = last_seen_to
                else:
                    params['last_seen__lt'] = last_seen_to
            queryset = queryset.filter(**params)

        if active_at_from or active_at_to:
            params = {}
            if active_at_from:
                if active_at_from_inclusive:
                    params['active_at__gte'] = active_at_from
                else:
                    params['active_at__gt'] = active_at_from
            if active_at_to:
                if active_at_to_inclusive:
                    params['active_at__lte'] = active_at_to
                else:
                    params['active_at__lt'] = active_at_to
            queryset = queryset.filter(**params)

        if times_seen is not None:
            queryset = queryset.filter(times_seen=times_seen)

        if times_seen_lower is not None or times_seen_upper is not None:
            params = {}
            if times_seen_lower is not None:
                if times_seen_lower_inclusive:
                    params['times_seen__gte'] = times_seen_lower
                else:
                    params['times_seen__gt'] = times_seen_lower
            if times_seen_upper is not None:
                if times_seen_upper_inclusive:
                    params['times_seen__lte'] = times_seen_upper
                else:
                    params['times_seen__lt'] = times_seen_upper
            queryset = queryset.filter(**params)

        if date_from or date_to:
            params = {
                'project_id': project.id,
            }
            if date_from:
                if date_from_inclusive:
                    params['datetime__gte'] = date_from
                else:
                    params['datetime__gt'] = date_from
            if date_to:
                if date_to_inclusive:
                    params['datetime__lte'] = date_to
                else:
                    params['datetime__lt'] = date_to

            event_queryset = Event.objects.filter(**params)

            if query:
                event_queryset = event_queryset.filter(
                    message__icontains=query)

            # limit to the first 1000 results
            group_ids = event_queryset.distinct().values_list(
                'group_id', flat=True)[:1000]

            # if Event is not on the primary database remove Django's
            # implicit subquery by coercing to a list
            base = router.db_for_read(Group)
            using = router.db_for_read(Event)
            # MySQL also cannot do a LIMIT inside of a subquery
            if base != using or engine.startswith('mysql'):
                group_ids = list(group_ids)

            queryset = queryset.filter(
                id__in=group_ids,
            )

        if engine.startswith('sqlite'):
            score_clause = SQLITE_SORT_CLAUSES[sort_by]
        elif engine.startswith('mysql'):
            score_clause = MYSQL_SORT_CLAUSES[sort_by]
        elif engine.startswith('oracle'):
            score_clause = ORACLE_SORT_CLAUSES[sort_by]
        elif engine in MSSQL_ENGINES:
            score_clause = MSSQL_SORT_CLAUSES[sort_by]
        else:
            score_clause = SORT_CLAUSES[sort_by]

        queryset = queryset.extra(
            select={'sort_value': score_clause},
        )
        return queryset

    def query(self, project, count_hits=False, paginator_options=None, **kwargs):
        if paginator_options is None:
            paginator_options = {}

        queryset = self._build_queryset(project=project, **kwargs)

        sort_by = kwargs.get('sort_by', 'date')
        limit = kwargs.get('limit', 100)
        cursor = kwargs.get('cursor')

        # HACK: don't sort by the same column twice
        if sort_by == 'date':
            paginator_cls = DateTimePaginator
            sort_clause = '-last_seen'
        elif sort_by == 'priority':
            paginator_cls = Paginator
            sort_clause = '-score'
        elif sort_by == 'new':
            paginator_cls = DateTimePaginator
            sort_clause = '-first_seen'
        elif sort_by == 'freq':
            paginator_cls = Paginator
            sort_clause = '-times_seen'
        else:
            paginator_cls = Paginator
            sort_clause = '-sort_value'

        queryset = queryset.order_by(sort_clause)
        paginator = paginator_cls(queryset, sort_clause, **paginator_options)
        return paginator.get_result(limit, cursor, count_hits=count_hits)


sort_strategies = {
    'priority': ('log(times_seen) * 600 + last_seen::abstime::int', int),
    'date': ('last_seen', lambda score: int(to_timestamp(score) * 1000)),
    'new': ('first_seen', lambda score: int(to_timestamp(score) * 1000)),
    'freq': ('times_seen', int),
}


import operator
from sentry.utils.cursors import Cursor, CursorResult


class SequencePaginator(object):
    def __init__(self, data, reverse=False):
        self.data = sorted(data, reverse=reverse)
        self.reverse = reverse

    def get_result(self, limit, cursor=None):
        if cursor is None:
            cursor = (None, 0, False)

        cursor_score, cursor_offset, cursor_previous = cursor

        assert cursor_offset > -1

        if cursor_score is None:
            position = 0 if not cursor_previous else len(self.data)
        else:
            position = 0
            # TODO: This point could be identified with binary search.
            predicate = operator.ge if not self.reverse else operator.le
            while position < len(self.data):
                score, value = self.data[position]
                if predicate(score, cursor_score):
                    break
                else:
                    position = position + 1

        position = position + cursor_offset

        if not cursor_previous:
            lo = max(position, 0)
            hi = min(lo + limit, len(self.data))
        else:
            # TODO: It might make sense to ensure that this hi value is at
            # least the length of the page + 1 if we want to ensure we return a
            # full page of results when paginating backwards while data is
            # being mutated.
            hi = min(position, len(self.data))
            lo = max(hi - limit, 0)

        results = map(
            lambda (score, item): item,
            self.data[lo:hi],
        )

        prev_cursor = None
        if lo > 0:
            prev_score = self.data[lo][0]
            prev_offset = 0
            # TODO: This point could be identified with binary search.
            while lo - prev_offset - 1 > -1 and prev_score == self.data[lo - prev_offset - 1][0]:
                prev_offset = prev_offset + 1
            prev_cursor = (prev_score, prev_offset, True, True)

        next_cursor = None
        if hi < len(self.data):
            next_score = self.data[hi][0]
            # TODO: This point could be identified with binary search.
            next_offset = 0
            while hi - next_offset - 1 > -1 and next_score == self.data[hi - next_offset - 1][0]:
                next_offset = next_offset + 1
            next_cursor = (next_score, next_offset, False, True)

        return CursorResult(
            results,
            prev=Cursor(*prev_cursor) if prev_cursor is not None else None,
            next=Cursor(*next_cursor) if next_cursor is not None else None,
            hits=len(self.data),
            max_hits=1000,  # XXX
        )


def scalar(parameter, field, operator):
    return (
        lambda queryset, value, inclusive: queryset.filter(**{
            '{}__{}{}'.format(
                field,
                operator,
                'e' if inclusive else ''
            ): value,
        }),
        ['{}_inclusive'.format(parameter)],
    )


undefined = object()


class QueryBuilder(object):
    def __init__(self, handlers):
        self.handlers = handlers

    def build(self, queryset, parameters):
        for parameter, (handler, extra_parameters) in self.handlers.items():
            value = parameters.get(parameter, undefined)
            if value is not undefined:
                queryset = handler(
                    queryset,
                    value,
                    *[parameters[name] for name in extra_parameters]
                )

        return queryset


class Column(namedtuple('Column', 'model field')):
    def __str__(self):
        return '"{}"."{}"'.format(*[
            self.model._meta.db_table,
            self.model._meta.get_field_by_name(self.field)[0].column,
        ])


class EnvironmentDjangoSearchBackend(SearchBackend):
    def query(self,
              project,
              tags=None,
              sort_by='date',
              count_hits=False,
              paginator_options=None,
              environment_id=None,
              cursor=None,
              limit=None,
              **kwargs
              ):
        from sentry.models import Environment, Group

        environment_id = Environment.objects.get(
            projects=project,
            name=tags['environment'],
        ).id

        # TODO(tkaemming): I don't know where this goes?

        """
        if date_from is not None:
            raise NotImplementedError

        if date_to is not None:
            raise NotImplementedError
        """

        result = SequencePaginator(
            self.filter_candidates(
                project,
                environment_id,
                tags,
                sort_by,
                candidates=self.find_candidates(
                    project,
                    environment_id,
                    **kwargs
                ),
                **kwargs
            ),
            reverse=True,
        ).get_result(limit, cursor)

        # lol
        result.results = filter(
            None,
            map(
                Group.objects.in_bulk(result.results).get,
                result.results,
            ),
        )

        return result

    def find_candidates(self, project, environment_id, **kwargs):
        # TODO(tkaemming): If no filters are provided it might make sense to
        # return from this method without making a query, letting the query run
        # unrestricted in `filter_candidates`.

        from sentry.models import Group, GroupEnvironment, GroupSubscription, GroupStatus, Release

        queryset = QueryBuilder({
            'first_release': (
                lambda queryset, version: queryset.extra(
                    where=[
                        '{} = {}'.format(
                            Column(GroupEnvironment, 'first_release_id'),
                            Column(Release, 'id'),
                        ),
                        '{} = %s'.format(
                            Column(Release, 'organization'),
                        ),
                        '{} = %s'.format(
                            Column(Release, 'version'),
                        ),
                    ],
                    params=[project.organization_id, version],
                    tables=[Release._meta.db_table],
                ),
                [],
            ),
            'query': (
                lambda queryset, query: queryset.filter(
                    Q(message__icontains=query) | Q(culprit__icontains=query),
                ) if query else queryset,
                [],
            ),
            'status': (
                lambda queryset, status: queryset.filter(status=status),
                [],
            ),
            'bookmarked_by': (
                lambda queryset, user: queryset.filter(
                    bookmark_set__project=project,
                    bookmark_set__user=user,
                ),
                [],
            ),
            'assigned_to': (
                lambda queryset, user: queryset.filter(
                    assignee_set__project=project,
                    assignee_set__user=user,
                ),
                [],
            ),
            'unassigned': (
                lambda queryset, unassigned: queryset.filter(
                    assignee_set__isnull=unassigned,
                ),
                [],
            ),
            'subscribed_by': (
                lambda queryset, user: queryset.filter(
                    id__in=GroupSubscription.objects.filter(
                        project=project,
                        user=user,
                        is_active=True,
                    ).values_list('group'),
                ),
                [],
            ),
            'active_at_from': scalar('active_at_from', 'active_at', 'gt'),
            'active_at_to': scalar('active_at_to', 'active_at', 'lt'),
        }).build(
            Group.objects.filter(project=project).exclude(status__in=[
                GroupStatus.PENDING_DELETION,
                GroupStatus.DELETION_IN_PROGRESS,
                GroupStatus.PENDING_MERGE,
            ]),
            # .extra(
            #     where=[
            #         '{} = {}'.format(
            #             Column(Group, 'id'),
            #             Column(GroupEnvironment, 'group_id'),
            #         ),
            #         '{} = %s'.format(
            #             Column(GroupEnvironment, 'environment_id'),
            #         ),
            #     ],
            #     params=[environment_id],
            #     tables=[GroupEnvironment._meta.db_table],
            # ),
            kwargs
        )

        # TODO(tkaemming): This shoould also utilize some of the scalar
        # attributes from `find_candidates` to rule out entries that are
        # impossible based on aggregate attributes (e.g. an issue cannot be
        # seen in an environment after the issue's last seen timestamp.)

        # TODO(tkaemming): This queryset should probably have a limit
        # associated with it? If there is one, it should be greater than (or
        # equal to) the "maximum hits" number if we want that to reflect a
        # realistic estimate.

        return set(queryset.values_list('id', flat=True))

    def filter_candidates(self, project, environment_id, tags, sort_by, **kwargs):
        # TODO(tkaemming): This shouldn't be implemented like this, since this
        # is an abstraction leak from tagstore, but it's good enough to prove
        # the point for now.

        from sentry.search.base import ANY
        from sentry.tagstore.models import GroupTagKey, GroupTagValue

        sort_expression, value_to_cursor_score = sort_strategies[sort_by]

        queryset = QueryBuilder({
            'candidates': (
                lambda queryset, candidates: queryset.filter(group_id__in=candidates),
                [],
            ),
            'age_from': scalar('age_from', 'first_seen', 'gt'),
            'age_to': scalar('age_to', 'first_seen', 'lt'),
            'last_seen_from': scalar('last_seen_from', 'last_seen', 'gt'),
            'last_seen_to': scalar('last_seen_to', 'last_seen', 'lt'),
            'times_seen': (
                lambda queryset, times_seen: queryset.filter(times_seen=times_seen),
                [],
            ),
            'times_seen_lower': scalar('times_seen_lower', 'times_seen', 'gt'),
            'times_seen_upper': scalar('times_seen_upper', 'times_seen', 'lt'),
        }).build(
            GroupTagValue.objects.filter(
                project_id=project.id,
                key='environment',
                value=tags.pop('environment'),
            ),
            kwargs
        ).extra(select={
            'sort_key': sort_expression,
        })

        candidates = dict(queryset.values_list('group_id', 'sort_key'))

        # TODO: Sort the remaining tags by estimated selectivity to try and
        # make this as efficient as possible.
        for key, value in tags.items():
            if value is ANY:
                queryset = GroupTagKey.objects.filter(
                    key=key,
                    group_id__in=candidates.keys(),
                )
            else:
                queryset = GroupTagValue.objects.filter(
                    key=key,
                    value=value,
                    group_id__in=candidates.keys(),
                )

            for id in set(candidates) - set(queryset.values_list('group_id', flat=True)):
                del candidates[id]

        return map(
            lambda (id, score): (
                value_to_cursor_score(score),
                id,
            ),
            candidates.items(),
        )
