import React, { useState } from 'react';
import Alert from 'react-bootstrap/Alert';
import * as Icon from 'react-bootstrap-icons';

export default function ErrorMessage(props) {
    const [message, ] = useState(props.message);

    return <Alert variant="danger"><Icon.ExclamationTriangle style={{color:"red", marginRight: "10px"}}/>{message}</Alert>
}
