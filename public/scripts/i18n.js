(() => {
  const settingsStorageKey = "games-library-settings";
  const legacySettingKeys = {
    language: "games-library-language",
    theme: "games-library-theme",
  };

  function readSettings() {
    try {
      const settings = JSON.parse(localStorage.getItem(settingsStorageKey) || "{}");
      return settings && typeof settings === "object" && !Array.isArray(settings) ? settings : {};
    } catch {
      return {};
    }
  }

  function writeSetting(name, value) {
    const settings = readSettings();
    settings[name] = value;
    try {
      localStorage.setItem(settingsStorageKey, JSON.stringify(settings));
    } catch {
      // The setting remains active for this page when storage is unavailable.
    }
  }

  function migrateLegacySettings() {
    try {
      const settings = readSettings();
      let changed = false;
      for (const [name, key] of Object.entries(legacySettingKeys)) {
        const legacyValue = localStorage.getItem(key);
        if (!Object.hasOwn(settings, name) && legacyValue !== null) {
          settings[name] = legacyValue;
          changed = true;
        }
      }

      if (changed) {
        localStorage.setItem(settingsStorageKey, JSON.stringify(settings));
      }
      for (const key of Object.values(legacySettingKeys)) {
        localStorage.removeItem(key);
      }
    } catch {
      // Keep legacy values available if storage cannot complete the migration.
    }
  }

  migrateLegacySettings();
  window.gamesLibrarySettings = {
    get: (name) => readSettings()[name],
    set: writeSetting,
  };

  const translations = {
    pt: {
      "Language": "Idioma", "Theme": "Tema", "Games API / personal library": "Games API / biblioteca pessoal",
      "Game Shelf": "Biblioteca de jogos", "Game Release Shelf": "Lançamentos de jogos",
      "Auto": "Automático", "White": "Claro", "Dark": "Escuro", "Glassmorphism": "Vidro",
      "Liquid glass": "Vidro líquido", "Sunset Vibes": "Pôr do sol", "Cyber Retro Gaming": "Retro cibernético", "Sign in": "Iniciar sessão", "Username": "Utilizador",
      "Password": "Palavra-passe", "Open shelf": "Abrir biblioteca", "Log out": "Terminar sessão",
      "Your collection": "A sua coleção", "Your collection of games releases": "Lançamentos de jogos",
      "Search titles or genres": "Pesquisar títulos ou géneros", "Search games": "Pesquisar jogos",
      "All platforms": "Todas as plataformas", "Platforms": "Plataformas", "Game details": "Detalhes do jogo",
      "No screenshot image": "Sem imagem de captura de ecrã", "No cover image": "Sem imagem de capa",
      "Achievements": "Conquistas", "Admin dashboard": "Painel de administração",
      "Games releases": "Lançamentos de jogos", "Games": "Jogos", "A quiet place for the games, you keep coming back to.": "Um lugar tranquilo para os jogos aos quais regressa sempre.",
      "Created by ": "Criado por ", " - All rights are reserved to LCP": " - Todos os direitos reservados a LCP",
      "Year": "Ano", "Month": "Mês", "Day": "Dia", "Limit": "Limite", "Load releases": "Carregar lançamentos",
      "First": "Primeira", "Previous": "Anterior", "Next": "Seguinte", "Last": "Última",
      "Close details": "Fechar detalhes", "Release pages": "Páginas de lançamentos",
      "LCPGAMELIB": "LCPGAMELIB", "LIBRARY ADMIN": "ADMINISTRAÇÃO DA BIBLIOTECA",
      "Overview": "Visão geral", "Releases": "Lançamentos", "Settings": "Definições", "API": "API",
      "Games Library admin home": "Página inicial da administração da biblioteca",
      "PRIVATE COLLECTION / ADMIN ACCESS": "COLEÇÃO PRIVADA / ACESSO DE ADMINISTRAÇÃO",
      "Your library,": "A sua biblioteca,", "at a glance.": "num relance.",
      "Sign in with an administrator account to continue.": "Inicie sessão com uma conta de administrador para continuar.",
      "Open dashboard": "Abrir painel", "LIVE SNAPSHOT": "RESUMO EM TEMPO REAL",
      "Good to see you": "Que bom ver-vos", "A clear view of what is in your library.": "Uma visão clara do que existe na sua biblioteca.",
      "Refresh data": "Atualizar dados", "Collection summary": "Resumo da coleção",
      "GAMES IN LIBRARY": "JOGOS NA BIBLIOTECA", "Titles in your collection": "Títulos na sua coleção",
      "TIME PLAYED": "TEMPO JOGADO", " hrs": " h", "Across all saved games": "Em todos os jogos guardados",
      "PLAYER RATING": "CLASSIFICAÇÃO DOS JOGADORES", "Critic average -- / 100": "Média da crítica -- / 100",
      "Critic average ": "Média da crítica ", "WISHLIST": "LISTA DE DESEJOS", "Games on your radar": "Jogos que tem debaixo de olho",
      "COLLECTION RECORDS": "REGISTOS DA COLEÇÃO", "Manage games and achievements": "Gerir jogos e conquistas",
      "Record type": "Tipo de registo", "Achievements": "Conquistas", "Hide records": "Ocultar registos",
      "Show records": "Mostrar registos", "Game records": "Registos de jogos",
      "Select a game to read or edit": "Selecione um jogo para consultar ou editar", "New game": "Novo jogo",
      "Create game": "Criar jogo", "Edit game": "Editar jogo", "Delete game": "Eliminar jogo",
      "Title": "Título", "Genre": "Género", "Release year": "Ano de lançamento", "Release date": "Data de lançamento",
      "Description": "Descrição", "Platforms": "Plataformas", "Game modes": "Modos de jogo", "Editions": "Edições",
      "ESRB rating": "Classificação ESRB", "Player rating": "Classificação dos jogadores",
      "Critic rating": "Classificação da crítica", "Hours played": "Horas jogadas", "Cover image URL": "URL da capa",
      "Image URL": "URL da imagem", "Screenshot URL": "URL da captura de ecrã", "On wishlist": "Na lista de desejos",
      "Save game": "Guardar jogo", "Game": "Jogo", "Achievement records": "Registos de conquistas",
      "Select an achievement to read or edit": "Selecione uma conquista para consultar ou editar",
      "New achievement": "Nova conquista", "Create achievement": "Criar conquista", "Edit achievement": "Editar conquista",
      "Delete achievement": "Eliminar conquista", "Points": "Pontos", "Status": "Estado", "Locked": "Bloqueada",
      "Unlocked": "Desbloqueada", "Type": "Tipo", "Unlocked date": "Data de desbloqueio", "Save achievement": "Guardar conquista",
      "Cancel edit": "Cancelar edição", "PAGE SETTINGS": "DEFINIÇÕES DA PÁGINA", "Page settings": "Definições da página",
      "LOCAL PREFS": "PREFERÊNCIAS LOCAIS", "Show recent additions": "Mostrar adições recentes",
      "Show release timeline": "Mostrar cronologia de lançamentos", "Compact dashboard view": "Vista compacta do painel",
      "Auto refresh": "Atualização automática", "Manual only": "Apenas manual", "Every 30 seconds": "A cada 30 segundos",
      "Every minute": "A cada minuto", "Every 5 minutes": "A cada 5 minutos", "Library charts": "Gráficos da biblioteca",
      "THE COLLECTION": "A COLEÇÃO", "Release timeline": "Cronologia de lançamentos", "TITLES / YEAR": "TÍTULOS / ANO",
      "Games in the library by release year": "Jogos na biblioteca por ano de lançamento",
      "No release years to chart yet.": "Ainda não há anos de lançamento para mostrar.",
      "Completion": "Conclusão", " TOTAL": " NO TOTAL", "Achievement completion rate": "Taxa de conclusão das conquistas",
      "UNLOCKED": "DESBLOQUEADAS", "Still locked": "Ainda bloqueadas", "Manage achievements": "Gerir conquistas",
      "By type": "Por tipo", "ALL GAMES": "TODOS OS JOGOS", "BY CATEGORY": "POR CATEGORIA",
      "Top genres": "Géneros principais", "MOST GAMES": "MAIS JOGOS", "WHERE YOU PLAY": "ONDE JOGA",
      "Recently catalogued": "Adicionados recentemente", "RECENTLY CATALOGUED": "ADICIONADOS RECENTEMENTE",
      "Latest in the library": "Mais recentes na biblioteca", "Open game shelf": "Abrir biblioteca de jogos",
      "TITLE": "TÍTULO", "RELEASE YEAR": "ANO DE LANÇAMENTO", "RECORD": "REGISTO",
      "Your library is ready for its first game.": "A sua biblioteca está pronta para o primeiro jogo.",
      "LCPGAMELIB / GAMES LIBRARY": "LCPGAMELIB / BIBLIOTECA DE JOGOS", "LOCAL COLLECTION DATA": "DADOS LOCAIS DA COLEÇÃO",
      "Login unlock countdown": "Contagem para desbloquear o início de sessão",
      "Loading your shelf...": "A carregar a biblioteca...", "The game collection could not be loaded.": "Não foi possível carregar a coleção de jogos.",
      "No description yet.": "Ainda sem descrição.", "Uncategorized": "Sem categoria", "View details": "Ver detalhes",
      "Not set": "Não definido", "Not Rated": "Sem classificação", "Yes": "Sim", "No": "Não",
      "Minimum system requirements": "Requisitos mínimos do sistema",
      "Recommended system requirements": "Requisitos de sistema recomendados",
      "No system requirements have been added for this game.": "Não foram adicionados requisitos de sistema para este jogo.",
      "Loading achievements...": "A carregar conquistas...", "Achievements could not be loaded.": "Não foi possível carregar as conquistas.",
      "No description.": "Sem descrição.", "No achievements for this game yet.": "Este jogo ainda não tem conquistas.",
      "Signing in...": "A iniciar sessão...", "Incorrect username or password.": "Nome de utilizador ou palavra-passe incorretos.",
      "Signed in, but your profile could not be loaded.": "Sessão iniciada, mas não foi possível carregar o seu perfil.",
      "Your profile could not be loaded.": "Não foi possível carregar o seu perfil.",
      "The server could not be reached.": "Não foi possível contactar o servidor.",
      "Login is temporarily locked.": "O início de sessão está temporariamente bloqueado.",
      "You could not be logged out.": "Não foi possível terminar a sessão.",
      "Login unlocked. You can try again.": "Início de sessão desbloqueado. Pode tentar novamente.",
      "Try again in {seconds} {unit}.": "Tente novamente dentro de {seconds} {unit}.",
      "Date for next games releases: {date}": "Data dos próximos lançamentos de jogos: {date}",
      "{count} game": "{count} jogo", "{count} games": "{count} jogos",
      "{count} platforms": "{count} plataformas",
      "{count} TOTAL": "{count} NO TOTAL",
      "Page": "Página", "of {total}": "de {total}", "Current page": "Página atual",
      "{count} of {total} unlocked": "{count} de {total} desbloqueadas",
      "{points} points": "{points} pontos", "Delete {title} and its achievements?": "Eliminar {title} e as respetivas conquistas?",
      "Delete achievement {title}?": "Eliminar a conquista {title}?", "Edit game #{id}": "Editar jogo n.º {id}",
      "Edit achievement #{id}": "Editar conquista n.º {id}", "{percent}% of achievements unlocked": "{percent}% das conquistas desbloqueadas",
      "{games} TITLES / {achievements} ACHIEVEMENTS": "{games} JOGOS / {achievements} CONQUISTAS",
      "Admin / Games Library": "Administração / Biblioteca de jogos",
      "Main navigation": "Navegação principal", "Filter by platform": "Filtrar por plataforma",
      "COLLECTION INTELLIGENCE /": "INTELIGÊNCIA DA COLEÇÃO /",
      "Achievements by type": "Conquistas por tipo", "Games by genre": "Jogos por género",
      "Games by platform": "Jogos por plataforma", "Loading records...": "A carregar registos...",
      "Updating collection data...": "A atualizar os dados da coleção...",
      "No games yet. Create the first game to add achievements.": "Ainda não há jogos. Crie o primeiro jogo para adicionar conquistas.",
      "Saving game changes...": "A guardar alterações ao jogo...", "Creating game...": "A criar jogo...",
      "Game saved.": "Jogo guardado.", "Deleting game...": "A eliminar jogo...", "Game deleted.": "Jogo eliminado.",
      "Create a game before adding achievements.": "Crie um jogo antes de adicionar conquistas.",
      "Saving achievement changes...": "A guardar alterações à conquista...", "Creating achievement...": "A criar conquista...",
      "Achievement saved.": "Conquista guardada.", "Deleting achievement...": "A eliminar conquista...",
      "Achievement deleted.": "Conquista eliminada.", "The request could not be completed.": "Não foi possível concluir o pedido.",
      "Dashboard data could not be loaded.": "Não foi possível carregar os dados do painel.",
      "Your session expired. Please sign in again.": "A sua sessão expirou. Inicie sessão novamente.",
      "This account does not have administrator access.": "Esta conta não tem acesso de administrador.",
      "No data to chart yet.": "Ainda não há dados para mostrar.", "TOTAL": "NO TOTAL",
      "ACHIEVEMENTS": "CONQUISTAS", "Recently catalogued": "Adicionados recentemente",
      "Created by": "Criado por", "All rights are reserved to LCP": "Todos os direitos reservados a LCP",
      "hrs": "h", "Edition": "Edição", "ESRB": "ESRB", "Wishlisted": "Na lista de desejos",
      "UPDATED {time}": "ATUALIZADO {time}", "Critic average {rating} / 100": "Média da crítica {rating} / 100",
      "User rating": "Classificação dos jogadores", "You have been signed out.": "Terminou a sessão.",
      "- All rights are reserved to LCP": "- Todos os direitos reservados a LCP",
      "Bronze": "Bronze", "Silver": "Prata", "Gold": "Ouro", "Platinum": "Platina",
    },
    de: {
      "Language": "Sprache", "Theme": "Design", "Games API / personal library": "Games API / persönliche Bibliothek",
      "Game Shelf": "Spielebibliothek", "Game Release Shelf": "Spielveröffentlichungen",
      "Auto": "Automatisch", "White": "Hell", "Dark": "Dunkel", "Glassmorphism": "Glasoptik",
      "Liquid glass": "Flüssiges Glas", "Sunset Vibes": "Sonnenuntergang", "Cyber Retro Gaming": "Cyber-Retro", "Sign in": "Anmelden", "Username": "Benutzername",
      "Password": "Passwort", "Open shelf": "Bibliothek öffnen", "Log out": "Abmelden",
      "Your collection": "Deine Sammlung", "Your collection of games releases": "Spielveröffentlichungen",
      "Search titles or genres": "Titel oder Genres suchen", "Search games": "Spiele suchen",
      "All platforms": "Alle Plattformen", "Platforms": "Plattformen", "Game details": "Spieldetails",
      "No screenshot image": "Kein Screenshot verfügbar", "No cover image": "Kein Cover verfügbar",
      "Achievements": "Erfolge", "Admin dashboard": "Admin-Dashboard",
      "Games releases": "Spielveröffentlichungen", "Games": "Spiele", "A quiet place for the games, you keep coming back to.": "Ein ruhiger Ort für die Spiele, zu denen du immer wieder zurückkehrst.",
      "Created by ": "Erstellt von ", " - All rights are reserved to LCP": " - Alle Rechte vorbehalten bei LCP",
      "Year": "Jahr", "Month": "Monat", "Day": "Tag", "Limit": "Limit", "Load releases": "Veröffentlichungen laden",
      "First": "Erste", "Previous": "Zurück", "Next": "Weiter", "Last": "Letzte",
      "Close details": "Details schließen", "Release pages": "Veröffentlichungsseiten",
      "LIBRARY ADMIN": "BIBLIOTHEKSADMIN", "Overview": "Übersicht", "Releases": "Veröffentlichungen",
      "Settings": "Einstellungen", "API": "API", "Games Library admin home": "Admin-Startseite der Spielebibliothek",
      "PRIVATE COLLECTION / ADMIN ACCESS": "PRIVATE SAMMLUNG / ADMIN-ZUGANG", "Your library,": "Deine Bibliothek,",
      "at a glance.": "auf einen Blick.", "Sign in with an administrator account to continue.": "Melde dich mit einem Administratorkonto an, um fortzufahren.",
      "Open dashboard": "Dashboard öffnen", "LIVE SNAPSHOT": "AKTUELLE ÜBERSICHT", "Good to see you": "Schön, dich zu sehen",
      "A clear view of what is in your library.": "Ein klarer Überblick über deine Bibliothek.", "Refresh data": "Daten aktualisieren",
      "Collection summary": "Sammlungsübersicht", "GAMES IN LIBRARY": "SPIELE IN DER BIBLIOTHEK",
      "Titles in your collection": "Titel in deiner Sammlung", "TIME PLAYED": "SPIELZEIT", " hrs": " Std.",
      "Across all saved games": "Über alle gespeicherten Spiele hinweg", "PLAYER RATING": "SPIELERBEWERTUNG",
      "Critic average -- / 100": "Kritikerdurchschnitt -- / 100", "Critic average ": "Kritikerdurchschnitt ",
      "WISHLIST": "WUNSCHLISTE", "Games on your radar": "Spiele, die du im Blick hast",
      "COLLECTION RECORDS": "SAMMLUNGSEINTRÄGE", "Manage games and achievements": "Spiele und Erfolge verwalten",
      "Record type": "Eintragstyp", "Hide records": "Einträge ausblenden", "Show records": "Einträge anzeigen",
      "Game records": "Spieleinträge", "Select a game to read or edit": "Spiel zum Anzeigen oder Bearbeiten auswählen",
      "New game": "Neues Spiel", "Create game": "Spiel erstellen", "Edit game": "Spiel bearbeiten",
      "Delete game": "Spiel löschen", "Title": "Titel", "Genre": "Genre", "Release year": "Erscheinungsjahr",
      "Release date": "Erscheinungsdatum", "Description": "Beschreibung", "Game modes": "Spielmodi",
      "Editions": "Editionen", "ESRB rating": "ESRB-Einstufung", "Player rating": "Spielerbewertung",
      "Critic rating": "Kritikerbewertung", "Hours played": "Gespielte Stunden", "Cover image URL": "Cover-Bild-URL",
      "Image URL": "Bild-URL", "Screenshot URL": "Screenshot-URL", "On wishlist": "Auf der Wunschliste",
      "Save game": "Spiel speichern", "Game": "Spiel", "Achievement records": "Erfolgseinträge",
      "Select an achievement to read or edit": "Erfolg zum Anzeigen oder Bearbeiten auswählen",
      "New achievement": "Neuer Erfolg", "Create achievement": "Erfolg erstellen", "Edit achievement": "Erfolg bearbeiten",
      "Delete achievement": "Erfolg löschen", "Points": "Punkte", "Status": "Status", "Locked": "Gesperrt",
      "Unlocked": "Freigeschaltet", "Type": "Typ", "Unlocked date": "Freischaltdatum", "Save achievement": "Erfolg speichern",
      "Cancel edit": "Bearbeitung abbrechen", "PAGE SETTINGS": "SEITENEINSTELLUNGEN", "Page settings": "Seiteneinstellungen",
      "LOCAL PREFS": "LOKALE EINSTELLUNGEN", "Show recent additions": "Neue Ergänzungen anzeigen",
      "Show release timeline": "Veröffentlichungszeitstrahl anzeigen", "Compact dashboard view": "Kompakte Dashboard-Ansicht",
      "Auto refresh": "Automatische Aktualisierung", "Manual only": "Nur manuell", "Every 30 seconds": "Alle 30 Sekunden",
      "Every minute": "Jede Minute", "Every 5 minutes": "Alle 5 Minuten", "Library charts": "Bibliotheksdiagramme",
      "THE COLLECTION": "DIE SAMMLUNG", "Release timeline": "Veröffentlichungszeitstrahl", "TITLES / YEAR": "TITEL / JAHR",
      "Games in the library by release year": "Spiele in der Bibliothek nach Erscheinungsjahr",
      "No release years to chart yet.": "Noch keine Erscheinungsjahre für das Diagramm vorhanden.",
      "Completion": "Abschluss", " TOTAL": " INSGESAMT", "Achievement completion rate": "Erfolgsabschlussrate",
      "UNLOCKED": "FREIGESCHALTET", "Still locked": "Noch gesperrt", "Manage achievements": "Erfolge verwalten",
      "By type": "Nach Typ", "ALL GAMES": "ALLE SPIELE", "BY CATEGORY": "NACH KATEGORIE",
      "Top genres": "Top-Genres", "MOST GAMES": "MEISTE SPIELE", "WHERE YOU PLAY": "WO DU SPIELST",
      "RECENTLY CATALOGUED": "KÜRZLICH ERFASST", "Latest in the library": "Neueste in der Bibliothek",
      "Open game shelf": "Spielebibliothek öffnen", "TITLE": "TITEL", "RELEASE YEAR": "ERSCHEINUNGSJAHR",
      "RECORD": "EINTRAG", "Your library is ready for its first game.": "Deine Bibliothek ist bereit für das erste Spiel.",
      "LCPGAMELIB / GAMES LIBRARY": "LCPGAMELIB / SPIELEBIBLIOTHEK", "LOCAL COLLECTION DATA": "LOKALE SAMMLUNGSDATEN",
      "Login unlock countdown": "Countdown bis zur Anmeldefreigabe", "Loading your shelf...": "Bibliothek wird geladen...",
      "The game collection could not be loaded.": "Die Spielesammlung konnte nicht geladen werden.",
      "No description yet.": "Noch keine Beschreibung.", "Uncategorized": "Ohne Kategorie", "View details": "Details anzeigen",
      "Not set": "Nicht festgelegt", "Not Rated": "Nicht bewertet", "Yes": "Ja", "No": "Nein",
      "Minimum system requirements": "Minimale Systemanforderungen",
      "Recommended system requirements": "Empfohlene Systemanforderungen",
      "No system requirements have been added for this game.": "Für dieses Spiel wurden keine Systemanforderungen hinzugefügt.",
      "Loading achievements...": "Erfolge werden geladen...", "Achievements could not be loaded.": "Erfolge konnten nicht geladen werden.",
      "No description.": "Keine Beschreibung.", "No achievements for this game yet.": "Dieses Spiel hat noch keine Erfolge.",
      "Signing in...": "Anmeldung läuft...", "Incorrect username or password.": "Benutzername oder Passwort falsch.",
      "Signed in, but your profile could not be loaded.": "Angemeldet, aber dein Profil konnte nicht geladen werden.",
      "Your profile could not be loaded.": "Dein Profil konnte nicht geladen werden.",
      "The server could not be reached.": "Der Server ist nicht erreichbar.",
      "Login is temporarily locked.": "Die Anmeldung ist vorübergehend gesperrt.",
      "You could not be logged out.": "Du konntest nicht abgemeldet werden.",
      "Login unlocked. You can try again.": "Anmeldung wieder freigeschaltet. Du kannst es erneut versuchen.",
      "Try again in {seconds} {unit}.": "Versuche es in {seconds} {unit} erneut.",
      "Date for next games releases: {date}": "Datum der nächsten Spielveröffentlichungen: {date}",
      "{count} game": "{count} Spiel", "{count} games": "{count} Spiele",
      "{count} platforms": "{count} Plattformen",
      "{count} TOTAL": "{count} INSGESAMT",
      "Page": "Seite", "of {total}": "von {total}", "Current page": "Aktuelle Seite",
      "{count} of {total} unlocked": "{count} von {total} freigeschaltet",
      "{points} points": "{points} Punkte", "Delete {title} and its achievements?": "{title} und seine Erfolge löschen?",
      "Delete achievement {title}?": "Erfolg {title} löschen?", "Edit game #{id}": "Spiel #{id} bearbeiten",
      "Edit achievement #{id}": "Erfolg #{id} bearbeiten", "{percent}% of achievements unlocked": "{percent}% der Erfolge freigeschaltet",
      "{games} TITLES / {achievements} ACHIEVEMENTS": "{games} SPIELE / {achievements} ERFOLGE",
      "Admin / Games Library": "Admin / Spielebibliothek",
      "Main navigation": "Hauptnavigation", "Filter by platform": "Nach Plattform filtern",
      "COLLECTION INTELLIGENCE /": "SAMMLUNGSÜBERSICHT /",
      "Achievements by type": "Erfolge nach Typ", "Games by genre": "Spiele nach Genre",
      "Games by platform": "Spiele nach Plattform", "Loading records...": "Einträge werden geladen...",
      "Updating collection data...": "Sammlungsdaten werden aktualisiert...",
      "No games yet. Create the first game to add achievements.": "Noch keine Spiele vorhanden. Erstelle das erste Spiel, um Erfolge hinzuzufügen.",
      "Saving game changes...": "Spieländerungen werden gespeichert...", "Creating game...": "Spiel wird erstellt...",
      "Game saved.": "Spiel gespeichert.", "Deleting game...": "Spiel wird gelöscht...", "Game deleted.": "Spiel gelöscht.",
      "Create a game before adding achievements.": "Erstelle ein Spiel, bevor du Erfolge hinzufügst.",
      "Saving achievement changes...": "Erfolgsänderungen werden gespeichert...", "Creating achievement...": "Erfolg wird erstellt...",
      "Achievement saved.": "Erfolg gespeichert.", "Deleting achievement...": "Erfolg wird gelöscht...",
      "Achievement deleted.": "Erfolg gelöscht.", "The request could not be completed.": "Die Anfrage konnte nicht abgeschlossen werden.",
      "Dashboard data could not be loaded.": "Dashboard-Daten konnten nicht geladen werden.",
      "Your session expired. Please sign in again.": "Deine Sitzung ist abgelaufen. Bitte melde dich erneut an.",
      "This account does not have administrator access.": "Dieses Konto hat keinen Administratorzugriff.",
      "No data to chart yet.": "Noch keine Daten für das Diagramm vorhanden.", "TOTAL": "INSGESAMT",
      "ACHIEVEMENTS": "ERFOLGE", "Recently catalogued": "Kürzlich erfasst", "Created by": "Erstellt von",
      "All rights are reserved to LCP": "Alle Rechte vorbehalten bei LCP", "hrs": "Std.",
      "Edition": "Edition", "ESRB": "USK", "Wishlisted": "Auf der Wunschliste",
      "UPDATED {time}": "AKTUALISIERT {time}", "Critic average {rating} / 100": "Kritikerdurchschnitt {rating} / 100",
      "User rating": "Spielerbewertung", "You have been signed out.": "Du wurdest abgemeldet.",
      "- All rights are reserved to LCP": "- Alle Rechte vorbehalten bei LCP",
      "Bronze": "Bronze", "Silver": "Silber", "Gold": "Gold", "Platinum": "Platin",
    },
    fr: {
      "Language": "Langue", "Theme": "Thème", "Games API / personal library": "Games API / bibliothèque personnelle",
      "Game Shelf": "Bibliothèque de jeux", "Game Release Shelf": "Sorties de jeux",
      "Auto": "Automatique", "White": "Clair", "Dark": "Sombre", "Glassmorphism": "Effet verre",
      "Liquid glass": "Verre liquide", "Sunset Vibes": "Coucher de soleil", "Cyber Retro Gaming": "Cyber rétro", "Sign in": "Se connecter", "Username": "Nom d’utilisateur",
      "Password": "Mot de passe", "Open shelf": "Ouvrir la bibliothèque", "Log out": "Se déconnecter",
      "Your collection": "Votre collection", "Your collection of games releases": "Sorties de jeux",
      "Search titles or genres": "Rechercher par titre ou genre", "Search games": "Rechercher des jeux",
      "All platforms": "Toutes les plateformes", "Platforms": "Plateformes", "Game details": "Détails du jeu",
      "No screenshot image": "Aucune capture d’écran", "No cover image": "Aucune jaquette",
      "Achievements": "Succès", "Admin dashboard": "Tableau de bord admin",
      "Games releases": "Sorties de jeux", "Games": "Jeux", "A quiet place for the games, you keep coming back to.": "Un endroit paisible pour les jeux auxquels vous revenez toujours.",
      "Created by ": "Créé par ", " - All rights are reserved to LCP": " - Tous droits réservés à LCP",
      "Year": "Année", "Month": "Mois", "Day": "Jour", "Limit": "Limite", "Load releases": "Charger les sorties",
      "First": "Première", "Previous": "Précédente", "Next": "Suivante", "Last": "Dernière",
      "Close details": "Fermer les détails", "Release pages": "Pages des sorties",
      "LIBRARY ADMIN": "ADMINISTRATION DE LA BIBLIOTHÈQUE", "Overview": "Vue d’ensemble",
      "Releases": "Sorties", "Settings": "Paramètres", "API": "API", "Games Library admin home": "Accueil admin de la bibliothèque de jeux",
      "PRIVATE COLLECTION / ADMIN ACCESS": "COLLECTION PRIVÉE / ACCÈS ADMIN", "Your library,": "Votre bibliothèque,",
      "at a glance.": "en un coup d’œil.", "Sign in with an administrator account to continue.": "Connectez-vous avec un compte administrateur pour continuer.",
      "Open dashboard": "Ouvrir le tableau de bord", "LIVE SNAPSHOT": "APERÇU EN DIRECT",
      "Good to see you": "Heureux de vous revoir", "A clear view of what is in your library.": "Une vue claire du contenu de votre bibliothèque.",
      "Refresh data": "Actualiser les données", "Collection summary": "Résumé de la collection",
      "GAMES IN LIBRARY": "JEUX DANS LA BIBLIOTHÈQUE", "Titles in your collection": "Titres dans votre collection",
      "TIME PLAYED": "TEMPS DE JEU", " hrs": " h", "Across all saved games": "Sur l’ensemble des jeux enregistrés",
      "PLAYER RATING": "NOTE DES JOUEURS", "Critic average -- / 100": "Moyenne des critiques -- / 100",
      "Critic average ": "Moyenne des critiques ", "WISHLIST": "LISTE DE SOUHAITS", "Games on your radar": "Jeux à surveiller",
      "COLLECTION RECORDS": "ENTRÉES DE LA COLLECTION", "Manage games and achievements": "Gérer les jeux et les succès",
      "Record type": "Type d’entrée", "Hide records": "Masquer les entrées", "Show records": "Afficher les entrées",
      "Game records": "Entrées de jeu", "Select a game to read or edit": "Sélectionnez un jeu à consulter ou modifier",
      "New game": "Nouveau jeu", "Create game": "Créer un jeu", "Edit game": "Modifier le jeu",
      "Delete game": "Supprimer le jeu", "Title": "Titre", "Genre": "Genre", "Release year": "Année de sortie",
      "Release date": "Date de sortie", "Description": "Description", "Game modes": "Modes de jeu",
      "Editions": "Éditions", "ESRB rating": "Classification ESRB", "Player rating": "Note des joueurs",
      "Critic rating": "Note des critiques", "Hours played": "Heures jouées", "Cover image URL": "URL de la jaquette",
      "Image URL": "URL de l’image", "Screenshot URL": "URL de la capture d’écran", "On wishlist": "Dans la liste de souhaits",
      "Save game": "Enregistrer le jeu", "Game": "Jeu", "Achievement records": "Entrées de succès",
      "Select an achievement to read or edit": "Sélectionnez un succès à consulter ou modifier",
      "New achievement": "Nouveau succès", "Create achievement": "Créer un succès", "Edit achievement": "Modifier le succès",
      "Delete achievement": "Supprimer le succès", "Points": "Points", "Status": "Statut", "Locked": "Verrouillé",
      "Unlocked": "Déverrouillé", "Type": "Type", "Unlocked date": "Date de déverrouillage", "Save achievement": "Enregistrer le succès",
      "Cancel edit": "Annuler la modification", "PAGE SETTINGS": "PARAMÈTRES DE LA PAGE", "Page settings": "Paramètres de la page",
      "LOCAL PREFS": "PRÉFÉRENCES LOCALES", "Show recent additions": "Afficher les ajouts récents",
      "Show release timeline": "Afficher la chronologie des sorties", "Compact dashboard view": "Vue compacte du tableau de bord",
      "Auto refresh": "Actualisation automatique", "Manual only": "Manuellement uniquement", "Every 30 seconds": "Toutes les 30 secondes",
      "Every minute": "Chaque minute", "Every 5 minutes": "Toutes les 5 minutes", "Library charts": "Graphiques de la bibliothèque",
      "THE COLLECTION": "LA COLLECTION", "Release timeline": "Chronologie des sorties", "TITLES / YEAR": "TITRES / ANNÉE",
      "Games in the library by release year": "Jeux de la bibliothèque par année de sortie",
      "No release years to chart yet.": "Aucune année de sortie à afficher pour le moment.",
      "Completion": "Progression", " TOTAL": " AU TOTAL", "Achievement completion rate": "Taux de succès débloqués",
      "UNLOCKED": "DÉVERROUILLÉS", "Still locked": "Encore verrouillés", "Manage achievements": "Gérer les succès",
      "By type": "Par type", "ALL GAMES": "TOUS LES JEUX", "BY CATEGORY": "PAR CATÉGORIE",
      "Top genres": "Genres principaux", "MOST GAMES": "PLUS DE JEUX", "WHERE YOU PLAY": "VOS PLATEFORMES",
      "RECENTLY CATALOGUED": "AJOUTÉS RÉCEMMENT", "Latest in the library": "Derniers jeux de la bibliothèque",
      "Open game shelf": "Ouvrir la bibliothèque de jeux", "TITLE": "TITRE", "RELEASE YEAR": "ANNÉE DE SORTIE",
      "RECORD": "ENTRÉE", "Your library is ready for its first game.": "Votre bibliothèque attend son premier jeu.",
      "LCPGAMELIB / GAMES LIBRARY": "LCPGAMELIB / BIBLIOTHÈQUE DE JEUX", "LOCAL COLLECTION DATA": "DONNÉES LOCALES DE LA COLLECTION",
      "Login unlock countdown": "Compte à rebours du déblocage de connexion", "Loading your shelf...": "Chargement de la bibliothèque...",
      "The game collection could not be loaded.": "Impossible de charger la collection de jeux.",
      "No description yet.": "Aucune description pour le moment.", "Uncategorized": "Sans catégorie", "View details": "Voir les détails",
      "Not set": "Non défini", "Not Rated": "Non noté", "Yes": "Oui", "No": "Non",
      "Minimum system requirements": "Configuration système minimale",
      "Recommended system requirements": "Configuration système recommandée",
      "No system requirements have been added for this game.": "Aucune configuration système n’a été ajoutée pour ce jeu.",
      "Loading achievements...": "Chargement des succès...", "Achievements could not be loaded.": "Impossible de charger les succès.",
      "No description.": "Aucune description.", "No achievements for this game yet.": "Ce jeu n’a pas encore de succès.",
      "Signing in...": "Connexion en cours...", "Incorrect username or password.": "Nom d’utilisateur ou mot de passe incorrect.",
      "Signed in, but your profile could not be loaded.": "Connecté, mais impossible de charger votre profil.",
      "Your profile could not be loaded.": "Impossible de charger votre profil.",
      "The server could not be reached.": "Impossible de joindre le serveur.",
      "Login is temporarily locked.": "La connexion est temporairement verrouillée.",
      "You could not be logged out.": "Impossible de vous déconnecter.",
      "Login unlocked. You can try again.": "Connexion déverrouillée. Vous pouvez réessayer.",
      "Try again in {seconds} {unit}.": "Réessayez dans {seconds} {unit}.",
      "Date for next games releases: {date}": "Date des prochaines sorties de jeux : {date}",
      "{count} game": "{count} jeu", "{count} games": "{count} jeux",
      "{count} platforms": "{count} plateformes",
      "{count} TOTAL": "{count} AU TOTAL",
      "Page": "Page", "of {total}": "sur {total}", "Current page": "Page actuelle",
      "{count} of {total} unlocked": "{count} sur {total} déverrouillés",
      "{points} points": "{points} points", "Delete {title} and its achievements?": "Supprimer {title} et ses succès ?",
      "Delete achievement {title}?": "Supprimer le succès {title} ?", "Edit game #{id}": "Modifier le jeu n° {id}",
      "Edit achievement #{id}": "Modifier le succès n° {id}", "{percent}% of achievements unlocked": "{percent}% des succès déverrouillés",
      "{games} TITLES / {achievements} ACHIEVEMENTS": "{games} JEUX / {achievements} SUCCÈS",
      "Admin / Games Library": "Admin / Bibliothèque de jeux",
      "Main navigation": "Navigation principale", "Filter by platform": "Filtrer par plateforme",
      "COLLECTION INTELLIGENCE /": "VUE D’ENSEMBLE DE LA COLLECTION /",
      "Achievements by type": "Succès par type", "Games by genre": "Jeux par genre",
      "Games by platform": "Jeux par plateforme", "Loading records...": "Chargement des entrées...",
      "Updating collection data...": "Mise à jour des données de la collection...",
      "No games yet. Create the first game to add achievements.": "Aucun jeu pour le moment. Créez le premier jeu pour ajouter des succès.",
      "Saving game changes...": "Enregistrement des modifications du jeu...", "Creating game...": "Création du jeu...",
      "Game saved.": "Jeu enregistré.", "Deleting game...": "Suppression du jeu...", "Game deleted.": "Jeu supprimé.",
      "Create a game before adding achievements.": "Créez un jeu avant d’ajouter des succès.",
      "Saving achievement changes...": "Enregistrement des modifications du succès...", "Creating achievement...": "Création du succès...",
      "Achievement saved.": "Succès enregistré.", "Deleting achievement...": "Suppression du succès...",
      "Achievement deleted.": "Succès supprimé.", "The request could not be completed.": "La requête n’a pas pu aboutir.",
      "Dashboard data could not be loaded.": "Impossible de charger les données du tableau de bord.",
      "Your session expired. Please sign in again.": "Votre session a expiré. Veuillez vous reconnecter.",
      "This account does not have administrator access.": "Ce compte ne dispose pas d’un accès administrateur.",
      "No data to chart yet.": "Aucune donnée à afficher pour le moment.", "TOTAL": "AU TOTAL",
      "ACHIEVEMENTS": "SUCCÈS", "Recently catalogued": "Ajoutés récemment", "Created by": "Créé par",
      "All rights are reserved to LCP": "Tous droits réservés à LCP", "hrs": "h",
      "Edition": "Édition", "ESRB": "ESRB", "Wishlisted": "Dans la liste de souhaits",
      "UPDATED {time}": "MIS À JOUR {time}", "Critic average {rating} / 100": "Moyenne des critiques {rating} / 100",
      "User rating": "Note des joueurs", "You have been signed out.": "Vous êtes déconnecté.",
      "- All rights are reserved to LCP": "- Tous droits réservés à LCP",
      "Bronze": "Bronze", "Silver": "Argent", "Gold": "Or", "Platinum": "Platine",
    },
  };

  const languageNames = {
    en: "English",
    pt: "Português",
    de: "Deutsch",
    fr: "Français",
  };
  const originalText = new WeakMap();
  const originalAttributes = new WeakMap();
  const generatedTextSources = new Map();
  let currentLanguage = "en";
  const languageSelector = document.getElementById("language-selector");
  const originalTitle = document.title;

  function matchTemplate(template, message) {
    const names = [];
    const pattern = template.split(/(\{\w+\})/g).map((part) => {
      const placeholder = part.match(/^\{(\w+)\}$/);
      if (placeholder) {
        names.push(placeholder[1]);
        return "(.+?)";
      }
      return part.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
    }).join("");
    if (!names.length) return null;
    const match = message.match(new RegExp(`^${pattern}$`));
    if (!match) return null;
    return Object.fromEntries(names.map((name, index) => [name, match[index + 1]]));
  }

  function translate(message, values = {}) {
    const localizedMessages = translations[currentLanguage] || {};
    let template = localizedMessages[message];
    let matchedValues = {};
    if (!template) {
      for (const [source, localized] of Object.entries(localizedMessages)) {
        const match = matchTemplate(source, message);
        if (match) {
          template = localized;
          matchedValues = match;
          break;
        }
      }
    }
    template ||= message;
    const translated = template.replace(
      /\{(\w+)\}/g,
      (_, name) => values[name] ?? matchedValues[name] ?? `{${name}}`,
    );
    if (currentLanguage !== "en" && Object.keys(values).length) {
      generatedTextSources.set(
        translated,
        message.replace(/\{(\w+)\}/g, (_, name) => values[name] ?? `{${name}}`),
      );
    }
    return translated;
  }

  function findSourceText(message) {
    if (generatedTextSources.has(message)) return generatedTextSources.get(message);
    const localizedMessages = Object.entries(translations[currentLanguage] || {});
    const exactMatch = localizedMessages.find(([, localized]) => localized === message);
    if (exactMatch) return exactMatch[0];

    for (const [source, localized] of localizedMessages) {
      const match = matchTemplate(localized, message);
      if (match) return source.replace(/\{(\w+)\}/g, (_, name) => match[name]);
    }
    return message;
  }

  function translateTextNode(node) {
    if (node.parentElement?.closest('[translate="no"]')) return;
    if (!originalText.has(node)) originalText.set(node, findSourceText(node.nodeValue));
    const source = originalText.get(node);
    const match = source.match(/^(\s*)([\s\S]*?)(\s*)$/);
    const translated = translate(match[2]);
    const result = `${match[1]}${translated}${match[3]}`;
    if (node.nodeValue !== result) node.nodeValue = result;
  }

  function translateElement(element) {
    if (element.closest('[translate="no"]')) return;
    for (const attribute of ["placeholder", "aria-label", "title", "alt"]) {
      if (!element.hasAttribute(attribute)) continue;
      let originals = originalAttributes.get(element);
      if (!originals) {
        originals = new Map();
        originalAttributes.set(element, originals);
      }
      if (!originals.has(attribute)) originals.set(attribute, element.getAttribute(attribute));
      const translated = translate(originals.get(attribute));
      if (element.getAttribute(attribute) !== translated) element.setAttribute(attribute, translated);
    }
  }

  function translateDocument(root = document.body) {
    if (!root) return;
    if (root.nodeType === Node.TEXT_NODE) {
      translateTextNode(root);
      return;
    }
    if (root.nodeType === Node.ELEMENT_NODE) translateElement(root);
    const walker = document.createTreeWalker(root, NodeFilter.SHOW_TEXT);
    let node;
    while ((node = walker.nextNode())) translateTextNode(node);
    if (root.nodeType === Node.ELEMENT_NODE) {
      for (const element of root.querySelectorAll("*")) translateElement(element);
    }
  }

  function setLanguage(language) {
    currentLanguage = Object.hasOwn(languageNames, language) ? language : "en";
    document.documentElement.lang = currentLanguage;
    document.title = translate(originalTitle);
    if (languageSelector) languageSelector.value = currentLanguage;
    window.gamesLibrarySettings.set("language", currentLanguage);
    translateDocument();
    document.dispatchEvent(new CustomEvent("languagechange", { detail: { language: currentLanguage } }));
  }

  const savedLanguage = window.gamesLibrarySettings.get("language") || "en";
  setLanguage(savedLanguage);
  languageSelector?.addEventListener("change", () => setLanguage(languageSelector.value));

  const observer = new MutationObserver((mutations) => {
    for (const mutation of mutations) {
      if (mutation.type === "characterData") translateTextNode(mutation.target);
      for (const node of mutation.addedNodes) translateDocument(node);
      if (mutation.type === "attributes") translateElement(mutation.target);
    }
  });
  observer.observe(document.body, {
    attributes: true,
    attributeFilter: ["placeholder", "aria-label", "title", "alt"],
    characterData: true,
    childList: true,
    subtree: true,
  });

  window.i18n = {
    get language() {
      return currentLanguage;
    },
    languageNames,
    setLanguage,
    t: translate,
  };
})();
