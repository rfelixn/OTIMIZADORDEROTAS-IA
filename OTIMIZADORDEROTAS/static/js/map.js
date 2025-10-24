function initMap() {
    const map = new google.maps.Map(document.getElementById("map"), {
        zoom: 12,
        center: { lat: -23.5505, lng: -46.6333 }
    });

    const directionsService = new google.maps.DirectionsService();
    const directionsRenderer = new google.maps.DirectionsRenderer({ map: map });

    const waypoints = entregas.map(e => ({ location: e.endereco, stopover: true }));

    directionsService.route({
        origin: 'Endereço do depósito',
        destination: 'Endereço do depósito',
        waypoints: waypoints,
        optimizeWaypoints: true,
        travelMode: 'DRIVING'
    }, (result, status) => {
        if (status === 'OK') {
            directionsRenderer.setDirections(result);
        } else {
            console.error('Erro ao gerar rota:', status);
        }
    });
}