import React from 'react';
import {ThemeProvider} from 'emotion-theming';
import {mount} from 'enzyme';

import {Client} from 'app/api';

import ProjectGeneralSettings from 'app/views/projectGeneralSettings';
import theme from 'app/utils/theme';

jest.mock('jquery');

describe('projectGeneralSettings', function() {
  let org = TestStubs.Organization();
  let project = TestStubs.Project();

  beforeEach(function() {
    sinon.stub(window.location, 'assign');
    Client.clearMockResponses();
    Client.addMockResponse({
      url: `/projects/${org.slug}/${project.slug}/`,
      method: 'GET',
      body: project,
    });
  });

  afterEach(function() {
    window.location.assign.restore();
  });

  it('renders', function() {
    let component = mount(
      <ThemeProvider theme={theme}>
        <ProjectGeneralSettings params={{orgId: org.slug, projectId: project.slug}} />
      </ThemeProvider>,
      TestStubs.routerContext()
    );
    expect(component).toMatchSnapshot();
  });

  it('disables field with an org override', function() {
    let routerContext = TestStubs.routerContext();
    routerContext.context.organization.dataScrubber = true;
    let component = mount(
      <ThemeProvider theme={theme}>
        <ProjectGeneralSettings params={{orgId: org.slug, projectId: project.slug}} />
      </ThemeProvider>,
      routerContext
    );
    expect(component.find('Switch[name="dataScrubber"]').prop('isDisabled')).toBe(true);
  });

  it('project admins can remove project', function() {
    let deleteMock = Client.addMockResponse({
      url: `/projects/${org.slug}/${project.slug}/`,
      method: 'DELETE',
    });

    let component = mount(
      <ThemeProvider theme={theme}>
        <ProjectGeneralSettings params={{orgId: org.slug, projectId: project.slug}} />
      </ThemeProvider>,
      TestStubs.routerContext()
    );

    let removeBtn = component.find('.ref-remove-project').first();

    expect(removeBtn.prop('children')).toBe('Remove Project');

    // Click button
    removeBtn.simulate('click');

    // Confirm Modal
    component.find('Modal Button[priority="danger"]').simulate('click');

    expect(deleteMock).toHaveBeenCalled();
  });

  it('project admins can transfer project', function() {
    let deleteMock = Client.addMockResponse({
      url: `/projects/${org.slug}/${project.slug}/transfer/`,
      method: 'POST',
    });

    let component = mount(
      <ThemeProvider theme={theme}>
        <ProjectGeneralSettings params={{orgId: org.slug, projectId: project.slug}} />
      </ThemeProvider>,
      TestStubs.routerContext()
    );

    let removeBtn = component.find('.ref-transfer-project').first();

    expect(removeBtn.prop('children')).toBe('Transfer Project');

    // Click button
    removeBtn.simulate('click');

    // Confirm Modal
    component
      .find('input[name="email"]')
      .simulate('change', {target: {value: 'billy@sentry.io'}});
    component.find('Modal Button[priority="danger"]').simulate('click');

    expect(deleteMock).toHaveBeenCalledWith(
      `/projects/${org.slug}/${project.slug}/transfer/`,
      expect.objectContaining({
        method: 'POST',
        data: {
          email: 'billy@sentry.io',
        },
      })
    );
  });

  it('displays transfer/remove message for non-admins', function() {
    let routerContext = TestStubs.routerContext();
    routerContext.context.organization.access = ['org:read'];
    let component = mount(
      <ThemeProvider theme={theme}>
        <ProjectGeneralSettings params={{orgId: org.slug, projectId: project.slug}} />
      </ThemeProvider>,
      routerContext
    );

    expect(component.html()).toContain(
      'You do not have the required permission to remove this project.'
    );
    expect(component.html()).toContain(
      'You do not have the required permission to transfer this project.'
    );
  });
});
