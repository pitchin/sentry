import {t} from '../../locale';

// Export route to make these forms searchable by label/help
export const route = '/settings/organization/:orgId/project/:projectId/hooks/:hookId/';

const formGroups = [
  {
    // Form "section"/"panel"
    title: t('General'),
    fields: [
      {
        name: 'url',
        type: 'string',
        required: true,

        // additional data/props that is related to rendering of form field rather than data
        label: t('URL'),
        help: t('The URL which will receive events.'),
      },
    ],
  },
];

export default formGroups;
