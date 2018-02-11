import React from 'react';
import PropTypes from 'prop-types';
import createReactClass from 'create-react-class';
import {Box} from 'grid-emotion';

import {t} from '../../../locale';
import {
  addErrorMessage,
  addSuccessMessage,
} from '../../../actionCreators/settingsIndicator';
import AsyncView from '../../asyncView';
import ApiMixin from '../../../mixins/apiMixin';
import Form from '../components/forms/form';
import JsonForm from '../components/forms/jsonForm';
import serviceHookSettingsFields from '../../../data/forms/serviceHookSettings';
import SettingsPageHeader from '../components/settingsPageHeader';

const TOAST_DURATION = 10000;

const ServiceHookSettingsForm = createReactClass({
  displayName: 'ServiceHookSettingsForm',

  propTypes: {
    location: PropTypes.object,
    orgId: PropTypes.string.isRequired,
    projectId: PropTypes.string.isRequired,
    hookId: PropTypes.string.isRequired,
    access: PropTypes.object.isRequired,
    initialData: PropTypes.object.isRequired,
    onSave: PropTypes.func.isRequired,
  },

  mixins: [ApiMixin],

  render() {
    let {initialData, orgId, projectId, hookId, onSave, access} = this.props;

    return (
      <Form
        apiMethod="PUT"
        apiEndpoint={`/projects/${orgId}/${projectId}/hooks/${hookId}/`}
        saveOnBlur
        allowUndo
        initialData={initialData}
        onSubmitSuccess={(change, model, id) => {
          if (!model) return;

          let label = model.getDescriptor(id, 'label');

          if (!label) return;

          addSuccessMessage(
            `Changed ${label} from "${change.old}" to "${change.new}"`,
            TOAST_DURATION,
            {model, id}
          );

          // Special case for slug, need to forward to new slug
          if (typeof onSave === 'function') {
            onSave(initialData, model.initialData);
          }
        }}
        onSubmitError={error => {
          if (error.responseJSON && 'require2FA' in error.responseJSON)
            return addErrorMessage(
              'Unable to save change. Enable two-factor authentication on your account first.',
              TOAST_DURATION
            );
          return addErrorMessage('Unable to save change', TOAST_DURATION);
        }}
      >
        <Box>
          <JsonForm
            access={access}
            location={this.props.location}
            forms={serviceHookSettingsFields}
          />
        </Box>
      </Form>
    );
  },
});

export default class ProjectServiceHookDetails extends AsyncView {
  getEndpoints() {
    let {orgId, projectId, hookId} = this.props.params;
    return [['hook', `/projects/${orgId}/${projectId}/hooks/${hookId}/`]];
  }

  renderBody() {
    let {orgId, projectId, hookId} = this.props.params;
    return (
      <div>
        <SettingsPageHeader title={t('Service Hook Details')} />
        <ServiceHookSettingsForm
          {...this.props}
          orgId={orgId}
          projectId={projectId}
          hookId={hookId}
          initialData={{...this.state.hook}}
        />
      </div>
    );
  }
}
