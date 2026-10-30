"""Fotos del catálogo inicial, de Wikimedia Commons, redimensionadas. Su licencia exige citar al autor."""


def _foto(archivo, alt, autor, licencia, licencia_url, fuente):
    return {'imagen': f'images/destinos/{archivo}.jpg', 'alt': alt, 'autor': autor, 'licencia': licencia,
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
