import React from 'react';
import PropTypes from 'prop-types';
import Modal from 'react-bootstrap/lib/Modal';

import Button from './buttons/button';
import {t} from '../locale';

class Confirm extends React.PureComponent {
  static propTypes = {
    onConfirm: PropTypes.func.isRequired,
    confirmText: PropTypes.string.isRequired,
    cancelText: PropTypes.string.isRequired,
    priority: PropTypes.oneOf(['primary', 'danger']).isRequired,
    message: PropTypes.node,
    /**
     * Renderer that passes:
     * `doConfirm`: Allows renderer to perform confirm action
     * `doClose`: Allows renderer to toggle confirm modal
     */
    renderMessage: PropTypes.func,

    disabled: PropTypes.bool,
    onConfirming: PropTypes.func,
    onCancel: PropTypes.func,
  };

  static defaultProps = {
    priority: 'primary',
    cancelText: t('Cancel'),
    confirmText: t('Confirm'),
  };

  constructor(...args) {
    super(...args);

    this.state = {
      isModalOpen: false,
      disableConfirmButton: false,
    };
    this.confirming = false;
  }

  handleConfirm = e => {
    // `confirming` is used to make sure `onConfirm` is only called once
    if (!this.confirming) {
      this.props.onConfirm();
    }

    // Close modal
    this.setState({
      isModalOpen: false,
      disableConfirmButton: true,
    });
    this.confirming = true;
  };

  handleToggle = e => {
    let {onConfirming, onCancel, disabled} = this.props;
    if (disabled) return;

    // Current state is closed, means it will toggle open
    if (!this.state.isModalOpen) {
      if (typeof onConfirming === 'function') {
        onConfirming();
      }
    } else {
      if (typeof onCancel === 'function') {
        onCancel();
      }
    }

    // Toggle modal display state
    // Also always reset `confirming` when modal visibility changes
    this.setState(state => ({
      isModalOpen: !state.isModalOpen,
      disableConfirmButton: false,
    }));

    this.confirming = false;
  };

  render() {
    let {
      disabled,
      message,
      renderMessage,
      priority,
      confirmText,
      cancelText,
      children,
    } = this.props;

    let confirmMessage;

    if (typeof renderMessage === 'function') {
      confirmMessage = renderMessage({
        doConfirm: this.handleConfirm,
        doClose: this.handleToggle,
      });
    } else {
      confirmMessage = React.isValidElement(message) ? (
        message
      ) : (
        <p>
          <strong>{message}</strong>
        </p>
      );
    }

    return (
      <React.Fragment>
        {React.cloneElement(children, {disabled, onClick: this.handleToggle})}
        <Modal show={this.state.isModalOpen} animation={false} onHide={this.handleToggle}>
          <div className="modal-body">{confirmMessage}</div>
          <div className="modal-footer">
            <Button style={{marginRight: 10}} onClick={this.handleToggle}>
              {cancelText}
            </Button>
            <Button
              disabled={this.state.disableConfirmButton}
              priority={priority}
              onClick={this.handleConfirm}
            >
              {confirmText}
            </Button>
          </div>
        </Modal>
      </React.Fragment>
    );
  }
}

export default Confirm;
