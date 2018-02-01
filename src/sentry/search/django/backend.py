"""
sentry.search.django.backend
~~~~~~~~~~~~~~~~~~~~~~~~~~~~

:copyright: (c) 2010-2014 by the Sentry Team, see AUTHORS for more details.
:license: BSD, see LICENSE for more details.
"""

from __future__ import absolute_import

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


def add_scalar_filter(queryset, field, operator, value, inclusive):
    return queryset.filter(**{
        '{}__{}{}'.format(
            field,
            operator,
            'e' if inclusive else ''
        ): value,
    })


sort_expressions = {
    'priority': 'log(times_seen) * 600 + last_seen::abstime::int',
    'date': 'last_seen',
    'new': 'first_seen',
    'freq': 'times_seen',
}


class EnvironmentDjangoSearchBackend(SearchBackend):
    def query(self,
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
              age_from=None, age_from_inclusive=True,
              age_to=None, age_to_inclusive=True,
              last_seen_from=None, last_seen_from_inclusive=True,
              last_seen_to=None, last_seen_to_inclusive=True,
              date_from=None, date_from_inclusive=True,
              date_to=None, date_to_inclusive=True,
              active_at_from=None, active_at_from_inclusive=True,
              active_at_to=None, active_at_to_inclusive=True,
              times_seen=None,
              times_seen_lower=None, times_seen_lower_inclusive=True,
              times_seen_upper=None, times_seen_upper_inclusive=True,
              count_hits=False,
              paginator_options=None,
              environment_id=None,
              ):
        assert environment_id is not None  # TODO: This would need to support the None case.

        # TODO(tkaemming): I don't know where this goes?

        if date_from is not None:
            raise NotImplementedError

        if date_to is not None:
            raise NotImplementedError

        results = self.filter_candidates(
            project,
            environment_id,
            self.find_candidates(
                project,
                environment_id,
                query,
                status,
                bookmarked_by,
                assigned_to,
                unassigned,
                subscribed_by,
                active_at_from, active_at_from_inclusive,
                active_at_to, active_at_to_inclusive,
                first_release,
            ),
            tags,
            age_from, age_from_inclusive,
            age_to, age_to_inclusive,
            last_seen_from, last_seen_from_inclusive,
            last_seen_to, last_seen_to_inclusive,
            times_seen,
            times_seen_lower, times_seen_lower_inclusive,
            times_seen_upper, times_seen_upper_inclusive,
            sort_by,
        )

        raise NotImplementedError  # pagination

    def find_candidates(self,
                        project,
                        environment_id,
                        query=None,
                        status=None,
                        bookmarked_by=None,
                        assigned_to=None,
                        unassigned=None,
                        subscribed_by=None,
                        active_at_from=None, active_at_from_inclusive=True,
                        active_at_to=None, active_at_to_inclusive=True,
                        first_release=None,
                        ):
        # TODO(tkaemming): If no filters are provided it might make sense to
        # return from this method without making a query, letting the query run
        # unrestricted in `filter_candidates`.

        from sentry.models import Group, GroupSubscription, GroupStatus

        queryset = Group.objects.filter(project=project)

        if query:
            # TODO(dcramer): if we want to continue to support search on SQL
            # we should at least optimize this in Postgres so that it does
            # the query filter **after** the index filters, and restricts the
            # result set
            # XXX(tkaemming): This is not environment-aware
            queryset = queryset.filter(Q(message__icontains=query) | Q(culprit__icontains=query))

        if status is None:
            queryset = queryset.exclude(status__in=[
                GroupStatus.PENDING_DELETION,
                GroupStatus.DELETION_IN_PROGRESS,
                GroupStatus.PENDING_MERGE,
            ])
        else:
            queryset = queryset.filter(status=status)

        if bookmarked_by:
            queryset = queryset.filter(
                bookmark_set__project=project,
                bookmark_set__user=bookmarked_by,
            )

        if assigned_to is not None:
            assert unassigned is None
            queryset = queryset.filter(
                assignee_set__project=project,
                assignee_set__user=assigned_to,
            )

        if unassigned is not None:
            assert assigned_to is None
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

        # TODO(tkaemming): I'm not sure if this is the right place for these
        # checks but we don't track this on a per-environment basis and I'm not
        # entirely sure it makes sense to...?
        if active_at_from is not None:
            queryset = add_scalar_filter(
                queryset,
                'active_at',
                'gt',
                active_at_from,
                active_at_from_inclusive)

        if active_at_to is not None:
            queryset = add_scalar_filter(
                queryset,
                'active_at',
                'lt',
                active_at_to,
                active_at_to_inclusive)

        # TODO(tkaemming): Restrict the query to only those that have an
        # associated `GroupEnvironment` record (and limit to the first release,
        # if one is provided.) This could be done as a subquery, but preferably
        # it's done as a join against the `GroupEnvironment` table. This means
        # figuring out how to implement an ORM field that acts as a foreign key
        # for JOIN purposes, but isn't actually implemented as a foreign key
        # column under the hood.
        if first_release is not None:
            raise NotImplementedError

        # TODO(tkaemming): This shoould also utilize some of the scalar
        # attributes from `find_candidates` to rule out entries that are
        # impossible based on aggregate attributes (e.g. an issue cannot be
        # seen in an environment after the issue's last seen timestamp.)

        # TODO(tkaemming): This queryset should probably have a limit
        # associated with it? It should probably correspond to the maximum
        # number of hits as well.
        return set(queryset.values_list('id', flat=True))

    def filter_candidates(self,
                          project,
                          environment_id,
                          candidates=None,
                          tags=None,
                          age_from=None, age_from_inclusive=True,
                          age_to=None, age_to_inclusive=True,
                          last_seen_from=None, last_seen_from_inclusive=True,
                          last_seen_to=None, last_seen_to_inclusive=True,
                          times_seen=None,
                          times_seen_lower=None, times_seen_lower_inclusive=True,
                          times_seen_upper=None, times_seen_upper_inclusive=True,
                          sort_by='date',
                          ):
        # TODO(tkaemming): This shouldn't be implemented like this, since this
        # is an abstraction leak from tagstore, but it's good enough to prove
        # the point for now.

        from sentry.search.base import ANY
        from sentry.tagstore.models import GroupTagKey, GroupTagValue

        queryset = GroupTagValue.objects.filter(
            project_id=project.id,
            key='environment',
            value=tags.pop('environment'),
        )

        if candidates is not None:
            queryset = queryset.filter(group_id__in=candidates)

        if age_from is not None:
            queryset = add_scalar_filter(queryset, 'first_seen', 'gt', age_from, age_from_inclusive)

        if age_to is not None:
            queryset = add_scalar_filter(queryset, 'first_seen', 'lt', age_to, age_to_inclusive)

        if last_seen_from is not None:
            queryset = add_scalar_filter(
                queryset,
                'last_seen',
                'gt',
                last_seen_from,
                last_seen_from_inclusive)

        if last_seen_to is not None:
            queryset = add_scalar_filter(
                queryset,
                'last_seen',
                'lt',
                last_seen_to,
                last_seen_to_inclusive)

        if times_seen is not None:
            queryset = queryset.times_seen(times_seen=times_seen)

        if times_seen_lower is not None:
            queryset = add_scalar_filter(
                queryset,
                'times_seen',
                'gt',
                times_seen_lower,
                times_seen_lower_inclusive)

        if times_seen_upper is not None:
            queryset = add_scalar_filter(
                queryset,
                'times_seen',
                'lt',
                times_seen_upper,
                times_seen_upper_inclusive)

        queryset = queryset.extra(
            select={'sort_key': sort_expressions[sort_by]}
        )

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

        return sorted(
            candidates.items(),
            key=lambda (id, score): score,
            reverse=True,
        )
