"""Canal SSE global : le bus isole les personas et les tours publient leurs transitions."""
import asyncio

from jumeau import evenements, flux


def test_le_bus_ne_diffuse_qu_a_la_persona_abonnee():
    async def scenario():
        file = evenements.BUS.abonner("architecte")
        autre = evenements.BUS.abonner("conformite")
        try:
            evenements.publier("architecte", "tour.demarre", fil="travail-1")
            recu = await asyncio.wait_for(file.get(), 1)
            assert recu == {"type": "tour.demarre", "fil": "travail-1"}
            assert autre.empty()
        finally:
            evenements.BUS.desabonner("architecte", file)
            evenements.BUS.desabonner("conformite", autre)

    asyncio.run(scenario())


def test_un_tour_demarre_est_publie_a_son_proprietaire():
    async def scenario():
        file = evenements.BUS.abonner("architecte")

        async def produire(_emit):
            return {}

        try:
            reponse = flux.en_flux(produire, fil="travail-2", proprietaire="architecte")
            _ = [ligne async for ligne in reponse.body_iterator]
            recu = await asyncio.wait_for(file.get(), 1)
            assert recu["type"] == "tour.demarre"
            assert recu["fil"] == "travail-2"
        finally:
            for tid, tour in list(flux.TOURS.items()):
                if tour.fil == "travail-2":
                    flux.TOURS.pop(tid, None)
            evenements.BUS.desabonner("architecte", file)

    asyncio.run(scenario())


def test_une_fin_de_tour_est_publiee_a_son_proprietaire():
    async def scenario():
        file = evenements.BUS.abonner("architecte")
        tour = flux.Tour("travail-3", "architecte")
        flux.TOURS[tour.id] = tour
        try:
            await tour.terminer()
            recu = await asyncio.wait_for(file.get(), 1)
            assert recu["type"] == "tour.fini"
            assert recu["fil"] == "travail-3"
        finally:
            flux.TOURS.pop(tour.id, None)
            evenements.BUS.desabonner("architecte", file)

    asyncio.run(scenario())


def test_fermer_reveille_les_flux_pour_laisser_partir_le_serveur():
    async def scenario():
        file = evenements.BUS.abonner("architecte")
        evenements.fermer()
        recu = await asyncio.wait_for(file.get(), 1)
        assert recu == {"type": "fermeture"}
        assert not evenements.BUS._files

    asyncio.run(scenario())
