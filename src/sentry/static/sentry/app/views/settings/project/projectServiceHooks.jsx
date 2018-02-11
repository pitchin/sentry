import {Box} from 'grid-emotion';
import PropTypes from 'prop-types';
import {Link} from 'react-router';
import React from 'react';
import createReactClass from 'create-react-class';

import {t} from '../../../locale';
import ApiMixin from '../../../mixins/apiMixin';
import AsyncView from '../../asyncView';
import EmptyMessage from '../components/emptyMessage';
import Panel from '../components/panel';
import PanelBody from '../components/panelBody';
import PanelHeader from '../components/panelHeader';
import PanelItem from '../components/panelItem';
import SettingsPageHeader from '../components/settingsPageHeader';

const ServiceHookRow = createReactClass({
  displayName: 'ServiceHookRow',

  propTypes: {
    orgId: PropTypes.string.isRequired,
    projectId: PropTypes.string.isRequired,
    hook: PropTypes.object.isRequired,
  },

  mixins: [ApiMixin],

  getInitialState() {
    return {
      loading: false,
      error: false,
    };
  },

  render() {
    let {orgId, projectId, hook} = this.props;
    return (
      <PanelItem>
        <Box flex="1">
          <h5 style={{margin: '10px 0px'}}>
            <Link
              to={`/settings/organization/${orgId}/project/${projectId}/hooks/${hook.id}/`}
            >
              {hook.url}
            </Link>
          </h5>
        </Box>
      </PanelItem>
    );
  },
});

export default class ProjectServiceHooks extends AsyncView {
  getEndpoints() {
    let {orgId, projectId} = this.props.params;
    return [['hookList', `/projects/${orgId}/${projectId}/hooks/`]];
  }

  renderEmpty() {
    return (
      <EmptyMessage>
        {t('There are no service hooks associated with this project.')}
      </EmptyMessage>
    );
  }

  renderResults() {
    let {orgId, projectId} = this.props.params;

    return [
      <PanelHeader key={'header'}>{t('Service Hook')}</PanelHeader>,
      <PanelBody key={'body'}>
        {this.state.hookList.map(hook => {
          return (
            <ServiceHookRow
              key={hook.id}
              orgId={orgId}
              projectId={projectId}
              hook={hook}
            />
          );
        })}
      </PanelBody>,
    ];
  }

  renderBody() {
    let body;
    if (this.state.hookList.length > 0) body = this.renderResults();
    else body = this.renderEmpty();

    return (
      <div>
        <SettingsPageHeader title={t('Service Hooks')} />
        <Panel>{body}</Panel>
      </div>
    );
  }
}
