"""Fotos del catálogo inicial, de Wikimedia Commons, redimensionadas. Su licencia exige citar al autor."""


def _foto(archivo, alt, autor, licencia, licencia_url, fuente):
    return {'imagen': f'images/destinos/{archivo}.jpg', 'miniatura': f'images/destinos/{archivo}-m.jpg',
            'alt': alt, 'autor': autor, 'licencia': licencia,
            'licencia_url': licencia_url, 'fuente': 'https://commons.wikimedia.org/wiki/File:' + fuente}


BY_SA_2 = 'https://creativecommons.org/licenses/by-sa/2.0/'
BY_SA_3 = 'https://creativecommons.org/licenses/by-sa/3.0/'
BY_SA_4 = 'https://creativecommons.org/licenses/by-sa/4.0/'

FOTOS_CATALOGO = {
    'chapala': _foto('chapala', 'Torres de la parroquia de San Francisco en Chapala', 'AlejandroLinaresGarcia',
                     'CC BY-SA 4.0', BY_SA_4, 'Chapala156.JPG'),
    'mazamitla': _foto('mazamitla', 'Templo y plaza principal de Mazamitla', 'BicScope',
                       'CC BY-SA 3.0', BY_SA_3, 'TemploMazamitla.jpg'),
    'tapalpa': _foto('tapalpa', 'Templo de la Inmaculada Concepción y jardín de Tapalpa', 'Victor Daniel Rosales Lopez',
                     'CC BY-SA 3.0', BY_SA_3, 'Templo_de_la_Inmaculada_Concepci%C3%B3n_Tapalpa_1.JPG'),
    'guadalajara': _foto('guadalajara', 'Fachada del Hospicio Cabañas en Guadalajara', 'Fperezgo',
                         'CC BY-SA 3.0', BY_SA_3, 'Hospicio_caba%C3%B1as.JPG'),
    'tlaquepaque': _foto('tlaquepaque', 'Santuario de Nuestra Señora de la Soledad en Tlaquepaque',
                         'Juan Carlos Fonseca Mata', 'CC BY-SA 4.0', BY_SA_4,
                         'Nuestra_Se%C3%B1ora_de_la_Soledad_(Tlaquepaque)_3.jpg'),
    'ajijic': _foto('ajijic', 'Vista aérea del malecón de Ajijic y el lago de Chapala al atardecer', 'SimonVelazquez',
                    'CC BY-SA 4.0', BY_SA_4, 'Ajijic_Malecon_Sunset.jpg'),
    'guachimontones': _foto('guachimontones', 'Pirámide circular escalonada de Guachimontones, cubierta de pasto',
                            'Esteban Tucci', 'CC BY-SA 3.0', BY_SA_3, 'Guachimontones_Jalisco_-_Esteban_Tucci.jpg'),
    'mascota': _foto('mascota', 'Plaza de Mascota con su quiosco y la torre de la parroquia', 'AlbertKasillas',
                     'CC BY-SA 4.0', BY_SA_4, '2631931.jpg'),
    'talpa-de-allende': _foto('talpa-de-allende', 'Basílica de Nuestra Señora del Rosario en Talpa de Allende',
                              'Jrobertiko', 'CC BY-SA 3.0', BY_SA_3, 'Basilica_de_Nuestra_Senora_de_Talpa.JPG'),
    'barra-de-navidad': _foto('barra-de-navidad', 'Playa de Barra de Navidad con montañas al fondo',
                              'Fer Quintana', 'CC BY-SA 2.0', BY_SA_2, 'Barradenavidad.jpg'),
    'tonala': _foto('tonala', 'Templo amarillo de Santo Santiago Apóstol en Tonalá', 'Talton12',
                    'CC BY-SA 4.0', BY_SA_4, 'Santo_Santiago_Apostol.jpg'),
}

# Destinos importados, con fotos de los artículos de Wikipedia correspondientes, revisadas una por una.
FOTOS_CATALOGO.update({
    'casa-museo-lopez-portillo': _foto(
        'casa-museo-lopez-portillo', 'Fachada de la Casa Museo López Portillo en una esquina del centro de Guadalajara',
        'Fabián Vargas', 'CC BY-SA 3.0',
        'https://creativecommons.org/licenses/by-sa/3.0',
        'Casa_museo_LP2.jpg',
    ),
    'instituto-cultural-cabanas': _foto(
        'instituto-cultural-cabanas', 'Fachada y cúpula del Hospicio Cabañas en Guadalajara',
        'ProtoplasmaKid', 'CC BY-SA 4.0',
        'https://creativecommons.org/licenses/by-sa/4.0',
        'Hospicio_Caba%C3%B1as,_Guadalajara,_Jalisco_-_14.jpg',
    ),
    'isla-de-mezcala': _foto(
        'isla-de-mezcala', 'Isla de Mezcala en el lago de Chapala, vista desde la orilla',
        'Juliouß', 'CC BY-SA 4.0',
        'https://creativecommons.org/licenses/by-sa/4.0',
        'La_Isla_de_Mezcala.JPG',
    ),
    'morelos': _foto(
        'morelos', 'Esculturas blancas entre árboles en el Parque Morelos de Guadalajara',
        'Another Believer', 'CC BY-SA 4.0',
        'https://creativecommons.org/licenses/by-sa/4.0',
        'Guadalajara,_Jalisco,_Mexico_(2021)_-_388.jpg',
    ),
    'museo-regional-de-la-ceramica': _foto(
        'museo-regional-de-la-ceramica', 'Entrada y patio empedrado del Museo Regional de la Cerámica en Tlaquepaque',
        'Roberto J. Arceo', 'CC BY-SA 3.0',
        'https://creativecommons.org/licenses/by-sa/3.0',
        'Museo_Regional_de_la_Cer%C3%A1mica_de_Tlaquepaque_19.JPG',
    ),
    'museo-de-la-ciudad-guadalajara': _foto(
        'museo-de-la-ciudad-guadalajara', 'Corredor con arcos y plantas en el Museo de la Ciudad de Guadalajara',
        'Josfabs', 'CC BY-SA 3.0',
        'https://creativecommons.org/licenses/by-sa/3.0',
        'Museo_de_la_ciudad_guadalajara.JPG',
    ),
    'museo-del-periodismo-y-artes-graficas': _foto(
        'museo-del-periodismo-y-artes-graficas',
        'Fachada de piedra del Museo del Periodismo y las Artes Gráficas en Guadalajara',
        'Another Believer', 'CC BY-SA 4.0',
        'https://creativecommons.org/licenses/by-sa/4.0',
        'Guadalajara,_Jalisco,_Mexico_(2021)_-_440.jpg',
    ),
    'museo-etnografico-huichol-wixarika': _foto(
        'museo-etnografico-huichol-wixarika',
        'Interior del museo de arte huichol en Zapopan, con muros azules y vitrinas',
        'Thelmadatter', 'Dominio público',
        'https://commons.wikimedia.org/wiki/File:InsideMuseoHuicholZapopan.JPG',
        'InsideMuseoHuicholZapopan.JPG',
    ),
    'museo-nacional-del-tequila': _foto(
        'museo-nacional-del-tequila', 'Fachada roja del Museo Nacional del Tequila',
        'Juan Carlos Fonseca Mata', 'CC BY-SA 4.0',
        'https://creativecommons.org/licenses/by-sa/4.0',
        'Museo_Nacional_del_Tequila_(Tequila,_Jal.)_I.jpg',
    ),
    'museo-panteon-de-belen': _foto(
        'museo-panteon-de-belen', 'Portada de cantera del Panteón de Belén en Guadalajara',
        'Heterotrofo', 'CC BY-SA 4.0',
        'https://creativecommons.org/licenses/by-sa/4.0',
        'Guadalajara_Pante%C3%B3n_de_Bel%C3%A9n_ingreso.jpg',
    ),
    'museo-regional-de-guadalajara': _foto(
        'museo-regional-de-guadalajara', 'Fachada de cantera del Museo Regional de Guadalajara',
        'Another Believer', 'CC BY-SA 4.0',
        'https://creativecommons.org/licenses/by-sa/4.0',
        'Guadalajara,_Jalisco,_Mexico_(2021)_-_206.jpg',
    ),
    'palacio-de-gobierno': _foto(
        'palacio-de-gobierno', 'Vista aérea del Palacio de Gobierno de Jalisco y la Plaza de Armas',
        'Aurora Uribe Flores', 'CC BY-SA 4.0',
        'https://creativecommons.org/licenses/by-sa/4.0',
        'Palacio_de_Gobierno_Jalisco.jpg',
    ),
    'playa-mismaloya': _foto(
        'playa-mismaloya', 'Playa de Mismaloya con palmeras y montañas al fondo',
        'colorqueeny', 'CC BY-SA 3.0',
        'https://creativecommons.org/licenses/by-sa/3.0',
        'Mismaloya_Beach_-_panoramio_(1).jpg',
    ),
    'puente-matute-remus': _foto(
        'puente-matute-remus', 'Puente Matute Remus iluminado de noche',
        'AanikaP', 'CC BY 2.0',
        'https://creativecommons.org/licenses/by/2.0',
        'Puente_Matute_Remus_Gdl,_Mex..jpg',
    ),
})
