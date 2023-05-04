import React, { useState, useRef, useEffect } from 'react';
import Stack from 'react-bootstrap/Stack';
import Card from 'react-bootstrap/Card';
import Button from 'react-bootstrap/Button';
import Modal from 'react-bootstrap/Modal';
import Table from 'react-bootstrap/Table';
import Spinner from 'react-bootstrap/Spinner';
import * as Icon from 'react-bootstrap-icons';
import axios from 'axios';
import ErrorMessage from './ErrorMessage.js'
import getBackendUrlBase from './backendUrl.js'

export default function DockerCard(props) {
    const [dockerId, ] = useState(props.dockerId);
    const [focus, ] = useState(props.focus);
    const [modalVisible, setModalVisible] = useState(false);
    const [modalTitle, setModalTitle] = useState("");
    const [modalDisplayType, setModalDisplayType] = useState("");
    const [loadedData, setLoadedData] = useState(null);
    const [loadingData, setLoadingData] = useState(null);
    const [errorData, setErrorData] = useState(null);

    if (modalDisplayType !== "" && modalDisplayType !== "images" && modalDisplayType !== "containers") {
        console.error(`invalid modal display type ${modalDisplayType}`);
        setModalDisplayType("");
    }

    const myRef = useRef(null);

    useEffect(() => {
        if (focus)
            myRef.current.scrollIntoView();
    });

    const runDockerPrune = (dockerId) => {
        props.runTask('docker/'+dockerId+'/prune-images', 'Pruning images on '+dockerId)
    }

    const runDockerContainerPrune = (dockerId) => {
        props.runTask('docker/'+dockerId+'/prune-containers', 'Pruning containers on '+dockerId)
    }

    const listImages = (dockerId) => {
        setModalDisplayType("images");
        setModalVisible(true);
        setModalTitle(`list of images on "${dockerId}"`);

        const backendUrl = getBackendUrlBase() + 'docker/'
            + dockerId + '/images';

        setLoadingData(true);
        axios.get(backendUrl,
            { withCredentials: true }
        )
        .then(x => {
            setLoadedData(x.data);
            setLoadingData(false);
            setErrorData(false);
        })
        .catch(e => {
            setErrorData(e);
            setLoadingData(false);
        });
    }

    const listContainers = (dockerId) => {
        setModalDisplayType("containers");
        setModalVisible(true);
        setModalTitle(`list of containers on "${dockerId}"`);

        const backendUrl = getBackendUrlBase() + 'docker/'
            + dockerId + '/containers';

        setLoadingData(true);
        axios.get(backendUrl,
            { withCredentials: true }
        )
        .then(x => {
            setLoadedData(x.data);
            setLoadingData(false);
            setErrorData(false);
        })
        .catch(e => {
            setErrorData(e);
            setLoadingData(false);
        });
    }

    return (
        <React.Fragment>
        <Modal show={modalVisible} centered onHide={() => setModalVisible(false)} className="modal-lg">
        <Modal.Header closeButton>
            <Modal.Title>{modalTitle}</Modal.Title>
        </Modal.Header>
        <Modal.Body>
            { loadingData &&
                <div className="text-center">
                    <Spinner nimation="border" role="status" variant="primary">
                      <span className="visually-hidden">Loading...</span>
                    </Spinner>
                </div>
            }
            { errorData && <ErrorMessage message={errorData.message}/>
            }
            { loadedData && modalDisplayType === "images" && !loadingData && !errorData &&
                <div style={{ overflowY: 'auto', maxHeight: 'calc(100vh - 200px)' }}>
                <Table striped bordered hover style={{width: "100%", overflowY: 'auto', maxHeight: 'calc(100vh - 200px)'}}>
                <tbody>
                    {
                        loadedData.map(x => x.RepoTags.map(y => <tr><td>{y}</td></tr>))
                    }
                </tbody>
                </Table>
                </div>
            }
            { loadedData && modalDisplayType === "containers" && !loadingData && !errorData &&
                <div style={{ overflowY: 'auto', maxHeight: 'calc(100vh - 200px)' }}>
                <Table striped bordered hover style={{width: "100%"}}>
                <tbody>
                    {
                        loadedData.map(x => <tr><td>{x.Name}</td></tr>)
                    }
                </tbody>
                </Table>
                </div>
            }
        </Modal.Body>
        <Modal.Footer>
          <Button variant="secondary" onClick={() => setModalVisible(false)}>
            Close
          </Button>
        </Modal.Footer>
        </Modal>
        <Card ref={myRef} border="primary" className="shadow p-3 mb-5 bg-white rounded">
          <Card.Body>
            <Card.Title>
                    <div style={{ marginBottom: "20px" }} className="cardtitle me-auto text-start">
                        Docker instance <span style={{ fontWeight: "bold" }}>{dockerId}</span>
                    </div>
            </Card.Title>
                <Stack gap={3}>
                    <Button onClick={() => runDockerPrune(dockerId)} variant="outline-primary">
                        <Stack direction="horizontal" gap={1}><Icon.Eraser/><div>Prune images</div></Stack>
                    </Button>
                    <Button onClick={() => runDockerContainerPrune(dockerId)} variant="outline-primary">
                        <Stack direction="horizontal" gap={1}><Icon.EraserFill/><div>Prune containers</div></Stack>
                    </Button>
                    <Button onClick={() => listImages(dockerId)} variant="outline-primary">
                        <Stack direction="horizontal" gap={1}><Icon.List/><div>List images</div></Stack>
                    </Button>
                    <Button onClick={() => listContainers(dockerId)} variant="outline-primary">
                        <Stack direction="horizontal" gap={1}><Icon.ListCheck/><div>List containers</div></Stack>
                    </Button>
                </Stack>
          </Card.Body>
        </Card>
        </React.Fragment>
    )
}